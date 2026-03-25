from __future__ import annotations

from pathlib import Path

import cv2

from app.processing.document import detect_document_region
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
    previous_detection = None

    while True:
        success, frame = capture.read()
        if not success:
            break

        if frame_index % frame_interval == 0:
            if context.processing_mode == "camera":
                detection = detect_document_region(frame)
                processed_frame = detection.corrected_image
                transition_penalty = (
                    (0.25 if not detection.found else 0.0)
                    + max(0.0, 0.25 - detection.page_coverage)
                    + max(0.0, 0.2 - detection.rectangularity)
                    + (detection.occlusion_ratio * 0.9)
                )
                if previous_detection is not None:
                    transition_penalty += _camera_stability_penalty(previous_detection, detection)
            else:
                detection = None
                processed_frame = frame
                transition_penalty = 0.0

            quality = compute_frame_quality(
                processed_frame,
                mode=context.processing_mode,
                detection=detection,
                transition_penalty=transition_penalty,
            )
            sampled_frames.append(
                SampledFrame(
                    timestamp=frame_index / metadata.fps,
                    frame_index=frame_index,
                    image=processed_frame,
                    quality=quality,
                    detection=detection,
                )
            )
            previous_detection = detection
        frame_index += 1

    capture.release()

    if not sampled_frames:
        raise ValueError(
            f"No frames were sampled from {Path(context.upload_path).name}. "
            "The video may be unreadable or too short."
        )

    return sampled_frames


def _camera_stability_penalty(previous_detection, current_detection) -> float:
    if not previous_detection.found or not current_detection.found:
        return 0.18

    coverage_delta = abs(current_detection.page_coverage - previous_detection.page_coverage)
    rectangularity_delta = abs(current_detection.rectangularity - previous_detection.rectangularity)
    perspective_delta = abs(
        current_detection.perspective_score - previous_detection.perspective_score
    )
    return (
        min(coverage_delta * 1.8, 0.28)
        + min(rectangularity_delta * 0.9, 0.16)
        + min(perspective_delta * 0.75, 0.14)
    )
