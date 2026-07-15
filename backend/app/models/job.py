from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

JobStatus = Literal["queued", "processing", "ready", "failed", "cancelled"]
StageStatus = Literal["pending", "processing", "complete", "failed"]
PageStatus = Literal["active", "deleted"]
ExportStatus = Literal["idle", "processing", "ready", "failed"]
ProcessingMode = Literal["screen", "camera"]
OcrStatus = Literal["pending", "ready", "failed", "empty"]


@dataclass
class Progress:
    percent: int = 0
    message: str = "Waiting to start."


@dataclass
class EditPoint:
    x: float
    y: float


@dataclass
class CropBox:
    x: int
    y: int
    width: int
    height: int


@dataclass
class DrawStroke:
    color: str
    width: int
    points: list[EditPoint] = field(default_factory=list)
    # 1.0 = opaque pen; < 1.0 renders as a translucent highlighter stroke.
    opacity: float = 1.0


@dataclass
class TextAnnotation:
    text: str
    x: float
    y: float
    color: str = "#111111"
    font_size: int = 24


RegionMode = Literal["blur", "fill"]


@dataclass
class BlurRegion:
    x: int
    y: int
    width: int
    height: int
    intensity: int = 18
    # "blur" softens the region; "fill" redacts it with a solid color.
    mode: RegionMode = "blur"
    fill_color: str = "#000000"


PageFilter = Literal["none", "enhance", "grayscale", "bw"]


@dataclass
class PageEdits:
    rotation: int = 0
    # Small straightening angle in degrees (-15..15), applied after the
    # coarse 90° rotation and before cropping.
    fine_rotation: float = 0.0
    crop: CropBox | None = None
    filter: PageFilter = "none"
    # -100..100; 0 leaves the page untouched.
    brightness: int = 0
    contrast: int = 0
    strokes: list[DrawStroke] = field(default_factory=list)
    texts: list[TextAnnotation] = field(default_factory=list)
    blur_regions: list[BlurRegion] = field(default_factory=list)


@dataclass
class OcrBlock:
    text: str
    confidence: float
    top: int
    left: int


@dataclass
class Stage:
    key: str
    label: str
    status: StageStatus
    progress_percent: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class Page:
    id: str
    job_id: str
    order_index: int
    page_number: int
    preview_label: str
    thumbnail_url: str | None
    image_url: str | None
    sharpness_score: float
    segment_start: float
    segment_end: float
    source_frame_index: int
    source_timestamp: float
    manual: bool = False
    rotation: int = 0
    status: PageStatus = "active"
    deleted: bool = False
    source_image_url: str | None = None
    edits: PageEdits = field(default_factory=PageEdits)
    ocr_text: str | None = None
    ocr_blocks: list[OcrBlock] = field(default_factory=list)
    ocr_status: OcrStatus = "pending"
    ocr_error: str | None = None
    # Mean Tesseract word confidence (0-100); None when unknown or manually edited.
    ocr_confidence: float | None = None


@dataclass
class RejectedFrame:
    """A pipeline-dropped page candidate kept around so users can rescue it."""

    id: str
    timestamp: float
    source_frame_index: int
    reason: str
    score: float
    image_url: str | None = None
    thumbnail_url: str | None = None


@dataclass
class ExportArtifact:
    status: ExportStatus = "idle"
    progress_percent: int = 0
    filename: str | None = None
    download_url: str | None = None
    tex_url: str | None = None
    requested_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


Sensitivity = Literal["fewer", "balanced", "more"]
CameraOutput = Literal["cleaned", "color"]


@dataclass
class Job:
    id: str
    filename: str
    processing_mode: ProcessingMode
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    current_stage_key: str | None = None
    progress: Progress = field(default_factory=Progress)
    notes: list[str] = field(default_factory=list)
    stages: list[Stage] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)
    rejected_frames: list[RejectedFrame] = field(default_factory=list)
    export: ExportArtifact = field(default_factory=ExportArtifact)
    text_export: ExportArtifact = field(default_factory=ExportArtifact)
    searchable_export: ExportArtifact = field(default_factory=ExportArtifact)
    upload_path: str | None = None
    source_url: str | None = None
    ocr_language: str = "eng"
    sensitivity: Sensitivity = "balanced"
    camera_output: CameraOutput = "cleaned"
    cancel_requested: bool = False
    trim_start: float | None = None
    trim_end: float | None = None
    # Source video dimensions, recorded when the pipeline reads the file.
    video_width: int | None = None
    video_height: int | None = None
