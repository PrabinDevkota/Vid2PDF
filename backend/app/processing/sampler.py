from app.processing.types import SampledFrame


def sample_frames(filename: str, fps: float) -> list[SampledFrame]:
    """Placeholder sampler for initial scaffold wiring."""
    return [
        SampledFrame(timestamp=0.0, frame_index=0, sharpness_score=0.62),
        SampledFrame(timestamp=1.2, frame_index=36, sharpness_score=0.79),
        SampledFrame(timestamp=2.5, frame_index=75, sharpness_score=0.66),
        SampledFrame(timestamp=4.0, frame_index=120, sharpness_score=0.84),
        SampledFrame(timestamp=5.3, frame_index=159, sharpness_score=0.71),
        SampledFrame(timestamp=6.8, frame_index=204, sharpness_score=0.88),
    ]
