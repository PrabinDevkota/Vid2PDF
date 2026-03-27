from dataclasses import dataclass, field
from typing import Literal

import numpy as np

ProcessingMode = Literal["screen", "camera"]


@dataclass
class VideoMetadata:
    fps: float
    frame_count: int
    width: int
    height: int
    duration_seconds: float


@dataclass
class DocumentDetection:
    found: bool
    contour: np.ndarray | None
    corrected_image: np.ndarray
    page_coverage: float
    rectangularity: float
    occlusion_ratio: float
    perspective_score: float
    single_page_score: float
    background_intrusion_ratio: float
    border_touch_ratio: float
    text_density: float
    contour_confidence: float
    gutter_ratio: float
    opposing_page_ratio: float
    normalized: bool


@dataclass
class FrameQuality:
    sharpness: float
    brightness: float
    contrast: float
    edge_density: float
    page_coverage: float
    rectangularity: float
    occlusion_ratio: float
    transition_penalty: float
    readability_score: float
    sharpness_score: float
    contrast_score: float
    brightness_score: float
    text_density: float
    single_page_score: float
    background_intrusion_ratio: float
    border_touch_ratio: float
    contour_confidence: float
    gutter_ratio: float
    opposing_page_ratio: float
    stability_score: float
    rejected: bool
    rejection_reasons: list[str]
    score: float
    perceptual_hash: str


@dataclass
class SampledFrame:
    timestamp: float
    frame_index: int
    image: np.ndarray | None
    quality: FrameQuality
    detection: DocumentDetection | None = None
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
    debug_dir: str
    debug_report_path: str
    artifact_base_url: str
    processing_mode: ProcessingMode
