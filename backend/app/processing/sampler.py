from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from app.processing.cancellation import JobCancelledError
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
    should_abort: Callable[[], bool] | None = None,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
) -> list[SampledFrame]:
    capture = cv2.VideoCapture(context.upload_path)
    if not capture.isOpened():
        raise ValueError(f"Could not read uploaded video: {context.upload_path}")

    last_frame = max(metadata.frame_count - 1, 0)
    start_frame = 0
    end_frame = last_frame
    if start_seconds is not None and start_seconds > 0:
        start_frame = min(int(start_seconds * metadata.fps), last_frame)
    if end_seconds is not None and end_seconds > 0:
        end_frame = min(int(end_seconds * metadata.fps), last_frame)
    if end_frame < start_frame:
        capture.release()
        raise ValueError("Trim range is empty: the end time must be after the start time.")

    effective_sample_fps = max(sample_fps, 0.25)
    frame_interval = max(int(round(metadata.fps / effective_sample_fps)), 1)
    sampled_frames: list[SampledFrame] = []
    frame_index = start_frame
    if start_frame > 0:
        capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    previous_detection = None
    previous_gray_small = None

    while frame_index <= end_frame:
        if (frame_index - start_frame) % frame_interval != 0:
            # grab() advances the decoder without the retrieve/color-convert
            # step, which is the expensive half of read() for skipped frames.
            if not capture.grab():
                break
            frame_index += 1
            continue

        success, frame = capture.read()
        if not success:
            break

        if should_abort is not None and should_abort():
            capture.release()
            raise JobCancelledError("Frame sampling aborted by cancellation request.")
        if context.processing_mode == "camera":
            detection = detect_document_region(frame)
            processed_frame = detection.corrected_image
            if not detection.found:
                # Phone/WhatsApp screen recordings often have no paper contour.
                # Keep a mild penalty instead of stacking uncapped detection failures.
                transition_penalty = 0.2
            else:
                transition_penalty = (
                    max(0.0, 0.42 - detection.page_coverage)
                    + max(0.0, 0.58 - detection.single_page_score)
                    + max(0.0, detection.background_intrusion_ratio - 0.08) * 1.2
                    + max(0.0, detection.border_touch_ratio - 0.05) * 0.8
                    + (detection.occlusion_ratio * 1.1)
                )
                if previous_detection is not None:
                    transition_penalty += _camera_stability_penalty(
                        previous_detection,
                        detection,
                    )
            transition_penalty = min(transition_penalty, 1.0)
        else:
            detection = None
            processed_frame = frame
            transition_penalty = 0.0

        gray_small = downscale_gray(processed_frame)
        if previous_gray_small is not None:
            transition_penalty += _frame_transition_penalty(previous_gray_small, gray_small)
            transition_penalty = min(transition_penalty, 1.0)

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
                gray_small=gray_small,
            )
        )
        previous_detection = detection
        previous_gray_small = gray_small
        frame_index += 1

    capture.release()

    if not sampled_frames:
        if start_frame > 0 or end_frame < last_frame:
            raise ValueError(
                f"No frames were sampled from {Path(context.upload_path).name} "
                "within the selected time range."
            )
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


GRAY_SMALL_SIZE = (320, 180)


def downscale_gray(frame: np.ndarray) -> np.ndarray:
    """Shared 320x180 grayscale used for all frame-to-frame comparisons."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, GRAY_SMALL_SIZE, interpolation=cv2.INTER_AREA)


def frame_gray_small(frame: SampledFrame) -> np.ndarray:
    """Return the cached downsampled gray, computing it for frames built
    outside the sampler (manual/restored pages)."""
    if frame.gray_small is None:
        frame.gray_small = downscale_gray(frame.image)
    return frame.gray_small


def _frame_transition_penalty(prev_small: np.ndarray, curr_small: np.ndarray) -> float:
    if prev_small.shape != curr_small.shape:
        prev_small = cv2.resize(prev_small, (curr_small.shape[1], curr_small.shape[0]))
    diff = cv2.absdiff(prev_small, curr_small)
    mean_diff = float(np.mean(diff) / 255.0)
    _, threshold = cv2.threshold(diff, 22, 255, cv2.THRESH_BINARY)
    moving_ratio = float(np.mean(threshold > 0))
    return min((moving_ratio * 0.85) + (mean_diff * 0.6), 0.65)
