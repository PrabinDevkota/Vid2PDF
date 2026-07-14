from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.settings import settings
from app.models.job import Job, Progress, Stage
from app.processing.cancellation import JobCancelledError
from app.processing.context import build_pipeline_context
from app.processing.sampler import load_video_metadata, sample_frames
from app.services.job_service import JobNotCancellableError, JobService


def _make_job(job_id: str, status: str) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id=job_id,
        filename="demo.mp4",
        processing_mode="screen",
        status=status,  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
        stages=[Stage(key="sample_frames", label="Sample frames", status="processing")],
        progress=Progress(percent=10, message="Working."),
    )


def test_cancel_queued_job_is_terminal_immediately(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    service._jobs["job-q"] = _make_job("job-q", "queued")

    response = service.cancel_job("job-q")

    assert response is not None
    assert response.status == "cancelled"
    assert service._jobs["job-q"].cancel_requested is True
    # A queued worker that later picks the job up must bail out untouched.
    service._run_pipeline_job("job-q")
    assert service._jobs["job-q"].status == "cancelled"


def test_cancel_processing_job_sets_flag_and_pipeline_stops(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    service._jobs["job-p"] = _make_job("job-p", "processing")

    response = service.cancel_job("job-p")

    assert response is not None
    assert response.status == "processing"  # worker has not noticed yet
    assert service._jobs["job-p"].cancel_requested is True
    with pytest.raises(JobCancelledError):
        service._check_cancelled("job-p")

    service._mark_cancelled("job-p")
    job = service._jobs["job-p"]
    assert job.status == "cancelled"
    assert job.completed_at is not None
    assert all(stage.status != "processing" for stage in job.stages)


def test_cancel_finished_job_conflicts(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    service._jobs["job-r"] = _make_job("job-r", "ready")

    with pytest.raises(JobNotCancellableError):
        service.cancel_job("job-r")


def test_cancel_missing_job_returns_none(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()

    assert service.cancel_job("nope") is None


def test_cancelled_state_survives_reload(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    service._jobs["job-s"] = _make_job("job-s", "queued")
    service.cancel_job("job-s")

    reloaded = JobService()
    job = reloaded._jobs["job-s"]
    assert job.status == "cancelled"
    assert job.cancel_requested is True
    # Cancelled jobs are terminal and must not be failed by crash recovery.
    assert "interrupted" not in job.progress.message.lower()


def _write_test_video(path: Path, frame_count: int = 48) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        24.0,
        (160, 120),
    )
    for index in range(frame_count):
        frame = np.full((120, 160, 3), (index * 5) % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_sample_frames_aborts_on_cancellation(tmp_path) -> None:
    video_path = tmp_path / "clip.mp4"
    _write_test_video(video_path)
    settings.storage_path = str(tmp_path)
    context = build_pipeline_context(
        job_id="job-abort",
        upload_path=str(video_path),
        processing_mode="screen",
    )
    metadata = load_video_metadata(str(video_path))

    with pytest.raises(JobCancelledError):
        sample_frames(
            context=context,
            metadata=metadata,
            sample_fps=24.0,
            should_abort=lambda: True,
        )

    # Without an abort callback the same video samples normally.
    frames = sample_frames(context=context, metadata=metadata, sample_fps=4.0)
    assert frames
