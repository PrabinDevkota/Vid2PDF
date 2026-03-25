from __future__ import annotations

import cv2
import numpy as np

from app.processing.types import SampledFrame, StableSegment


def detect_stable_segments(
    frames: list[SampledFrame],
    min_seconds: float,
    max_change_ratio: float = 0.045,
) -> list[StableSegment]:
    if not frames:
        return []

    for index, frame in enumerate(frames):
        if index == 0:
            frame.change_ratio = 0.0
            continue
        frame.change_ratio = _frame_change_ratio(frames[index - 1].image, frame.image)

    segments: list[StableSegment] = []
    current_frames = [frames[0]]

    for frame in frames[1:]:
        if frame.change_ratio <= max_change_ratio:
            current_frames.append(frame)
            continue

        segment = _build_segment(current_frames, min_seconds, len(segments) + 1)
        if segment is not None:
            segments.append(segment)
        current_frames = [frame]

    final_segment = _build_segment(current_frames, min_seconds, len(segments) + 1)
    if final_segment is not None:
        segments.append(final_segment)

    if not segments:
        fallback_segment = _build_segment(frames, 0.0, 1)
        if fallback_segment is not None:
            segments.append(fallback_segment)

    return segments


def _build_segment(
    frames: list[SampledFrame],
    min_seconds: float,
    segment_number: int,
) -> StableSegment | None:
    if not frames:
        return None

    duration = frames[-1].timestamp - frames[0].timestamp
    if duration < min_seconds and len(frames) < 2:
        return None

    if len(frames) > 2:
        candidate_frames = frames[1:-1]
        if not candidate_frames:
            candidate_frames = frames
    else:
        candidate_frames = frames

    mean_change_ratio = float(np.mean([frame.change_ratio for frame in frames])) if frames else 0.0
    return StableSegment(
        segment_id=f"segment-{segment_number}",
        start_time=frames[0].timestamp,
        end_time=frames[-1].timestamp,
        candidate_frames=candidate_frames,
        mean_change_ratio=mean_change_ratio,
    )


def _frame_change_ratio(previous_frame: np.ndarray, current_frame: np.ndarray) -> float:
    prev_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    prev_small = cv2.resize(prev_gray, (320, 180), interpolation=cv2.INTER_AREA)
    curr_small = cv2.resize(curr_gray, (320, 180), interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(prev_small, curr_small)
    _, threshold = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
    return float(np.mean(threshold > 0))
