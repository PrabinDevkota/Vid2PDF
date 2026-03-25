from __future__ import annotations

import logging

import cv2
import numpy as np

from app.processing.types import SampledFrame, StableSegment

logger = logging.getLogger(__name__)


def detect_stable_segments(
    frames: list[SampledFrame],
    min_seconds: float,
    max_change_ratio: float = 0.045,
    hash_distance_threshold: int = 10,
    mean_diff_threshold: float = 0.012,
) -> list[StableSegment]:
    if not frames:
        return []

    transition_scores: list[float] = []
    hash_distances: list[int] = []
    mean_diffs: list[float] = []

    for index, frame in enumerate(frames):
        if index == 0:
            frame.change_ratio = 0.0
            continue
        frame.change_ratio = _frame_change_ratio(frames[index - 1].image, frame.image)
        mean_diff = _mean_frame_difference(frames[index - 1].image, frame.image)
        hash_distance = _hash_distance(
            frames[index - 1].quality.perceptual_hash,
            frame.quality.perceptual_hash,
        )
        transition_score = (frame.change_ratio * 0.7) + (mean_diff * 0.3)
        transition_scores.append(transition_score)
        hash_distances.append(hash_distance)
        mean_diffs.append(mean_diff)

    segments: list[StableSegment] = []
    if not transition_scores:
        segment = _build_segment(frames, min_seconds, 1, 1)
        return [segment] if segment is not None else []

    adaptive_score_threshold = max(
        max_change_ratio,
        float(np.mean(transition_scores) + (np.std(transition_scores) * 0.9)),
    )
    adaptive_hash_threshold = max(
        hash_distance_threshold,
        int(np.percentile(hash_distances, 75)),
    )
    adaptive_mean_diff_threshold = max(
        mean_diff_threshold,
        float(np.mean(mean_diffs) + (np.std(mean_diffs) * 0.75)),
    )
    sample_spacing = _median_sample_spacing(frames)
    min_frames_per_segment = max(1, int(round(min_seconds / max(sample_spacing, 0.001))))
    min_frames_between_splits = max(1, min_frames_per_segment)

    transition_indices: list[int] = []
    for metric_index, transition_score in enumerate(transition_scores, start=1):
        previous_score = transition_scores[metric_index - 2] if metric_index - 2 >= 0 else -1.0
        next_score = transition_scores[metric_index] if metric_index < len(transition_scores) else -1.0
        is_local_peak = transition_score >= previous_score and transition_score >= next_score
        hash_distance = hash_distances[metric_index - 1]
        mean_diff = mean_diffs[metric_index - 1]
        is_transition = (
            is_local_peak
            and (
                transition_score >= adaptive_score_threshold
                or hash_distance >= adaptive_hash_threshold
                or mean_diff >= adaptive_mean_diff_threshold
            )
        )
        if not is_transition:
            continue

        if transition_indices and metric_index - transition_indices[-1] < min_frames_between_splits:
            if transition_score > transition_scores[transition_indices[-1] - 1]:
                transition_indices[-1] = metric_index
            continue
        transition_indices.append(metric_index)

    start_index = 0
    for transition_index in transition_indices:
        segment = _build_segment(
            frames[start_index:transition_index],
            min_seconds,
            len(segments) + 1,
            min_frames_per_segment,
        )
        if segment is not None:
            segments.append(segment)
        start_index = transition_index

    final_segment = _build_segment(
        frames[start_index:],
        min_seconds,
        len(segments) + 1,
        min_frames_per_segment,
    )
    if final_segment is not None:
        segments.append(final_segment)

    if not segments:
        fallback_segment = _build_segment(frames, 0.0, 1, 1)
        if fallback_segment is not None:
            segments.append(fallback_segment)

    logger.info(
        "Stable segment detection complete: sampled_frames=%s, segments=%s, split_events=%s, min_frames_per_segment=%s, min_seconds=%.2f, adaptive_score_threshold=%.4f, adaptive_hash_threshold=%s, adaptive_mean_diff_threshold=%.4f, max_change_seen=%.4f, max_hash_distance=%s, max_mean_diff=%.4f",
        len(frames),
        len(segments),
        len(transition_indices),
        min_frames_per_segment,
        min_seconds,
        adaptive_score_threshold,
        adaptive_hash_threshold,
        adaptive_mean_diff_threshold,
        max(frame.change_ratio for frame in frames),
        max(hash_distances) if hash_distances else 0,
        max(mean_diffs) if mean_diffs else 0.0,
    )
    return segments


def _build_segment(
    frames: list[SampledFrame],
    min_seconds: float,
    segment_number: int,
    min_frames_per_segment: int,
) -> StableSegment | None:
    if not frames:
        return None

    duration = frames[-1].timestamp - frames[0].timestamp
    if duration < min_seconds and len(frames) < min_frames_per_segment:
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


def _hash_distance(left_hash: str, right_hash: str) -> int:
    return (int(left_hash, 16) ^ int(right_hash, 16)).bit_count()


def _mean_frame_difference(previous_frame: np.ndarray, current_frame: np.ndarray) -> float:
    prev_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    prev_small = cv2.resize(prev_gray, (256, 144), interpolation=cv2.INTER_AREA)
    curr_small = cv2.resize(curr_gray, (256, 144), interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(prev_small, curr_small)
    return float(np.mean(diff) / 255.0)


def _median_sample_spacing(frames: list[SampledFrame]) -> float:
    if len(frames) < 2:
        return 0.25

    deltas = [
        max(frames[index].timestamp - frames[index - 1].timestamp, 0.001)
        for index in range(1, len(frames))
    ]
    return float(np.median(deltas))
