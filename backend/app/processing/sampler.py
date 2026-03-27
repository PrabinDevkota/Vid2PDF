from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

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
    previous_processed_frame = None

    while True:
        success, frame = capture.read()
        if not success:
            break

        if frame_index % frame_interval == 0:
            if context.processing_mode == "camera":
                detection = detect_document_region(frame)
                processed_frame = detection.corrected_image
                transition_penalty = (
                    (0.35 if not detection.found else 0.0)
                    + max(0.0, 0.42 - detection.page_coverage)
                    + max(0.0, 0.58 - detection.single_page_score)
                    + max(0.0, detection.background_intrusion_ratio - 0.08) * 1.2
                    + max(0.0, detection.border_touch_ratio - 0.05) * 0.8
                    + (detection.occlusion_ratio * 1.1)
                )
                if previous_detection is not None:
                    transition_penalty += _camera_stability_penalty(previous_detection, detection)
            else:
                detection = None
                processed_frame = frame
                transition_penalty = 0.0
            if previous_processed_frame is not None:
                transition_penalty += _frame_transition_penalty(previous_processed_frame, processed_frame)

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
            previous_processed_frame = processed_frame
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
        return 0.22

    coverage_delta = abs(current_detection.page_coverage - previous_detection.page_coverage)
    rectangularity_delta = abs(current_detection.rectangularity - previous_detection.rectangularity)
    perspective_delta = abs(
        current_detection.perspective_score - previous_detection.perspective_score
    )
    single_page_delta = abs(current_detection.single_page_score - previous_detection.single_page_score)
    border_touch_delta = abs(current_detection.border_touch_ratio - previous_detection.border_touch_ratio)
    return (
        min(coverage_delta * 2.0, 0.32)
        + min(rectangularity_delta * 1.0, 0.18)
        + min(perspective_delta * 0.8, 0.14)
        + min(single_page_delta * 0.9, 0.18)
        + min(border_touch_delta * 0.7, 0.12)
    )


def _frame_transition_penalty(previous_frame: np.ndarray, current_frame: np.ndarray) -> float:
    prev_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    prev_small = cv2.resize(prev_gray, (224, 224), interpolation=cv2.INTER_AREA)
    curr_small = cv2.resize(curr_gray, (224, 224), interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(prev_small, curr_small)
    mean_diff = float(np.mean(diff) / 255.0)
    _, threshold = cv2.threshold(diff, 22, 255, cv2.THRESH_BINARY)
    moving_ratio = float(np.mean(threshold > 0))
    return min((moving_ratio * 0.85) + (mean_diff * 0.6), 0.65)
