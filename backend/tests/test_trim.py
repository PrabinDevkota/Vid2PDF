from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.processing.context import build_pipeline_context
from app.processing.sampler import load_video_metadata, sample_frames


def _write_test_video(path: Path, frame_count: int = 96, fps: float = 24.0) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (160, 120),
    )
    for index in range(frame_count):
        frame = np.full((120, 160, 3), (index * 3) % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_sample_frames_respects_trim_range(tmp_path) -> None:
    video_path = tmp_path / "clip.mp4"
    _write_test_video(video_path)  # 4 seconds at 24 fps
    context = build_pipeline_context(
        job_id="job-trim",
        upload_path=str(video_path),
        processing_mode="screen",
    )
    metadata = load_video_metadata(str(video_path))

    frames = sample_frames(
        context=context,
        metadata=metadata,
        sample_fps=24.0,
        start_seconds=1.0,
        end_seconds=3.0,
    )

    assert frames
    assert all(1.0 <= frame.timestamp <= 3.05 for frame in frames)
    # Roughly two seconds of frames at full sample rate.
    assert len(frames) <= 24 * 2 + 2

    full_frames = sample_frames(context=context, metadata=metadata, sample_fps=24.0)
    assert len(full_frames) > len(frames)


def test_sample_frames_rejects_empty_trim_range(tmp_path) -> None:
    video_path = tmp_path / "clip.mp4"
    _write_test_video(video_path)
    context = build_pipeline_context(
        job_id="job-trim-bad",
        upload_path=str(video_path),
        processing_mode="screen",
    )
    metadata = load_video_metadata(str(video_path))

    with pytest.raises(ValueError, match="Trim range is empty"):
        sample_frames(
            context=context,
            metadata=metadata,
            sample_fps=24.0,
            start_seconds=3.0,
            end_seconds=1.0,
        )


def test_upload_rejects_invalid_trim_range() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/jobs/upload",
        files={"file": ("clip.mp4", b"not-a-real-video", "video/mp4")},
        data={"trim_start": "10", "trim_end": "5"},
    )
    assert response.status_code == 422
    assert "after trim start" in response.json()["detail"]


def test_from_url_rejects_negative_trim_start() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/jobs/from-url",
        json={"url": "https://example.com/video.mp4", "trimStart": -3},
    )
    assert response.status_code == 422
