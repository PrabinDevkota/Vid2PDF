from __future__ import annotations

from pathlib import Path

import cv2

from app.processing.scoring import compute_frame_quality
from app.processing.types import PipelineContext, SampledFrame, VideoMetadata


def load_video_metadata(video_path: str) -> VideoMetadata:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    capture.release()

    if fps <= 0 or frame_count <= 0:
        raise ValueError("Video metadata could not be determined.")

    return VideoMetadata(
        fps=fps,
        frame_count=frame_count,
        width=width,
        height=height,
        duration_seconds=frame_count / fps,
    )


def sample_frames(
    context: PipelineContext,
    metadata: VideoMetadata,
    sample_fps: float,
) -> list[SampledFrame]:
    capture = cv2.VideoCapture(context.upload_path)
    if not capture.isOpened():
        raise ValueError(f"Could not read uploaded video: {context.upload_path}")

    effective_sample_fps = max(sample_fps, 0.25)
    frame_interval = max(int(round(metadata.fps / effective_sample_fps)), 1)
    sampled_frames: list[SampledFrame] = []
    frame_index = 0

    while True:
        success, frame = capture.read()
        if not success:
            break

        if frame_index % frame_interval == 0:
            quality = compute_frame_quality(frame)
            sampled_frames.append(
                SampledFrame(
                    timestamp=frame_index / metadata.fps,
                    frame_index=frame_index,
                    image=frame,
                    quality=quality,
                )
            )
        frame_index += 1

    capture.release()

    if not sampled_frames:
        raise ValueError(
            f"No frames were sampled from {Path(context.upload_path).name}. "
            "The video may be unreadable or too short."
        )

    return sampled_frames
