from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PageResponse(BaseModel):
    id: str
    pageNumber: int
    previewLabel: str
    previewUrl: str | None
    sharpnessScore: float
    segmentStart: float
    segmentEnd: float
    rotation: int


class StageResponse(BaseModel):
    key: str
    label: str
    state: Literal["pending", "complete"]


class JobResponse(BaseModel):
    id: str
    filename: str
    status: Literal["queued", "processing", "ready", "failed"]
    createdAt: datetime
    notes: list[str]
    stages: list[StageResponse]
    pages: list[PageResponse]


class ExportResponse(BaseModel):
    filename: str
    downloadUrl: str | None
    pageCount: int
