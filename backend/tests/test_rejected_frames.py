from datetime import datetime, timezone

import numpy as np

from app.core.settings import settings
from app.models.job import ExportArtifact, Job
from app.processing.types import FrameQuality, SampledFrame, SelectedPage
from app.services.job_service import JobService


def _quality(score: float) -> FrameQuality:
    return FrameQuality(
        sharpness=score,
        brightness=0.5,
        contrast=0.5,
        edge_density=0.1,
        page_coverage=1.0,
        rectangularity=1.0,
        occlusion_ratio=0.0,
        transition_penalty=0.0,
        readability_score=score,
        sharpness_score=score,
        contrast_score=0.5,
        brightness_score=0.5,
        text_density=0.2,
        single_page_score=1.0,
        background_intrusion_ratio=0.0,
        border_touch_ratio=0.0,
        contour_confidence=1.0,
        gutter_ratio=0.0,
        opposing_page_ratio=0.0,
        stability_score=1.0,
        rejected=False,
        rejection_reasons=[],
        score=score,
        perceptual_hash="0",
    )


def _candidate(page_id: str, score: float, timestamp: float = 1.0) -> SelectedPage:
    image = np.full((120, 160, 3), int(score * 200) % 255, dtype=np.uint8)
    frame = SampledFrame(
        timestamp=timestamp,
        frame_index=int(timestamp * 24),
        image=image,
        quality=_quality(score),
    )
    return SelectedPage(
        page_id=page_id,
        page_number=0,
        label=f"Candidate {page_id}",
        source_segment_id=f"seg-{page_id}",
        segment_start=timestamp,
        segment_end=timestamp + 1.0,
        selected_frame=frame,
        image_path="",
        thumbnail_path="",
    )


def _make_job(job_id: str) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id=job_id,
        filename="demo.mp4",
        processing_mode="screen",
        status="ready",
        created_at=now,
        updated_at=now,
        export=ExportArtifact(status="ready", filename=f"{job_id}.pdf"),
    )


def test_store_rejected_frames_writes_artifacts_and_caps_count(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()

    candidates = [
        (_candidate(f"cand-{index}", score=index / 30.0, timestamp=float(index)), "Removed as a visual near-duplicate")
        for index in range(30)
    ]
    stored = service._store_rejected_frames("job-rej", candidates)

    assert len(stored) == service._MAX_REJECTED_FRAMES
    # Highest-scoring candidates are kept.
    assert stored[0].score >= stored[-1].score
    for item in stored:
        assert item.image_url and item.thumbnail_url
        assert service._resolve_storage_path(item.image_url).is_file()
        assert service._resolve_storage_path(item.thumbnail_url).is_file()


def test_restore_rejected_frame_promotes_to_page(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    job = _make_job("job-restore-rej")
    stored = service._store_rejected_frames(
        job.id,
        [(_candidate("cand-a", score=0.8, timestamp=2.5), "Collapsed as part of a page-turn sequence")],
    )
    job.rejected_frames = stored
    service._jobs[job.id] = job

    response = service.restore_rejected_frame(job.id, stored[0].id)

    assert response is not None
    assert len(response.pages) == 1
    page = response.pages[0]
    assert page.manual is True
    assert abs(page.sourceTimestamp - 2.5) < 1e-6
    assert response.rejectedFrames == []
    assert response.export.status == "idle"  # exports invalidated

    # Restoring the same frame again fails cleanly.
    assert service.restore_rejected_frame(job.id, stored[0].id) is None


def test_rejected_frames_survive_state_reload(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    job = _make_job("job-rej-persist")
    job.rejected_frames = service._store_rejected_frames(
        job.id,
        [(_candidate("cand-b", score=0.5), "Removed after OCR found near-duplicate text")],
    )
    service._jobs[job.id] = job
    service._save_jobs()

    reloaded = JobService()
    loaded = reloaded._jobs[job.id]
    assert len(loaded.rejected_frames) == 1
    assert loaded.rejected_frames[0].reason == "Removed after OCR found near-duplicate text"


def test_old_state_without_rejected_frames_loads(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    job = _make_job("job-legacy")
    service._jobs[job.id] = job
    payload = service._serialize_job(job)
    payload.pop("rejected_frames", None)

    legacy = service._deserialize_job(payload)
    assert legacy.rejected_frames == []
