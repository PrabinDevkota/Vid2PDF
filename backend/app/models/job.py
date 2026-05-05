from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

JobStatus = Literal["queued", "processing", "ready", "failed"]
StageStatus = Literal["pending", "processing", "complete", "failed"]
PageStatus = Literal["active", "deleted"]
ExportStatus = Literal["idle", "processing", "ready", "failed"]
ProcessingMode = Literal["screen", "camera"]


@dataclass
class Progress:
    percent: int = 0
    message: str = "Waiting to start."



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


@dataclass
class ExportArtifact:
    status: ExportStatus = "idle"
    progress_percent: int = 0
    filename: str | None = None
    download_url: str | None = None
    requested_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None



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
    export: ExportArtifact = field(default_factory=ExportArtifact)
    upload_path: str | None = None
