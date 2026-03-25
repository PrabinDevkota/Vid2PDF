from dataclasses import dataclass


@dataclass
class SampledFrame:
    timestamp: float
    frame_index: int
    sharpness_score: float


@dataclass
class StableSegment:
    segment_id: str
    start_time: float
    end_time: float
    candidate_frames: list[SampledFrame]


@dataclass
class SelectedPage:
    page_id: str
    page_number: int
    label: str
    source_segment_id: str
    selected_frame: SampledFrame
    preview_url: str | None = None
