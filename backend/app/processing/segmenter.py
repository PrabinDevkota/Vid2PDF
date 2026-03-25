from app.processing.types import SampledFrame, StableSegment


def detect_stable_segments(
    frames: list[SampledFrame], min_seconds: float
) -> list[StableSegment]:
    """Placeholder segmentation based on fixed buckets."""
    if not frames:
        return []

    return [
        StableSegment(
            segment_id="segment-1",
            start_time=0.0,
            end_time=2.6,
            candidate_frames=frames[:3],
        ),
        StableSegment(
            segment_id="segment-2",
            start_time=4.0,
            end_time=6.9,
            candidate_frames=frames[3:],
        ),
    ]
