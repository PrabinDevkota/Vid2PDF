from dataclasses import dataclass, field

import numpy as np


@dataclass
class VideoMetadata:
    fps: float
    frame_count: int
    width: int
    height: int
    duration_seconds: float


@dataclass
class FrameQuality:
    sharpness: float
    brightness: float
    contrast: float
    edge_density: float
    score: float
    perceptual_hash: str


@dataclass
class SampledFrame:
    timestamp: float
    frame_index: int
    image: np.ndarray | None
    quality: FrameQuality
    change_ratio: float = 1.0


@dataclass
class StableSegment:
    segment_id: str
    start_time: float
    end_time: float
    candidate_frames: list[SampledFrame]
    mean_change_ratio: float


@dataclass
class SelectedPage:
    page_id: str
    page_number: int
    label: str
    source_segment_id: str
    segment_start: float
    segment_end: float
    selected_frame: SampledFrame
    image_path: str
    thumbnail_path: str
    rotation: int = 0
    preview_url: str | None = None
    image_url: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class PipelineContext:
    job_id: str
    upload_path: str
    job_root: str
    page_dir: str
    thumbnail_dir: str
    artifact_base_url: str
