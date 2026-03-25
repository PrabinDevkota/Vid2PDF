from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

JobStatus = Literal["queued", "processing", "ready", "failed"]
StageState = Literal["pending", "complete"]


@dataclass
class Stage:
    key: str
    label: str
    state: StageState


@dataclass
class Page:
    id: str
    page_number: int
    preview_label: str
    preview_url: str | None
    sharpness_score: float
    segment_start: float
    segment_end: float
    rotation: int = 0


@dataclass
class Job:
    id: str
    filename: str
    status: JobStatus
    created_at: datetime
    notes: list[str] = field(default_factory=list)
    stages: list[Stage] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)
