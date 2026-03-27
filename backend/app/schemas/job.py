from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ProgressResponse(BaseModel):
    percent: int
    message: str


class StageResponse(BaseModel):
    key: str
    label: str
    status: Literal["pending", "processing", "complete", "failed"]
    progressPercent: int
    startedAt: datetime | None
    completedAt: datetime | None


class PageResponse(BaseModel):
    id: str
    jobId: str
    orderIndex: int
    pageNumber: int
    previewLabel: str
    thumbnailUrl: str | None
    imageUrl: str | None
    sharpnessScore: float
    segmentStart: float
    segmentEnd: float
    sourceFrameIndex: int
    sourceTimestamp: float
    rotation: int
    status: Literal["active", "deleted"]
    deleted: bool


class ExportResponse(BaseModel):
    status: Literal["idle", "processing", "ready", "failed"]
    progressPercent: int
    filename: str | None
    downloadUrl: str | None
    requestedAt: datetime | None
    completedAt: datetime | None
    error: str | None


class JobResponse(BaseModel):
    id: str
    filename: str
    processingMode: Literal["screen", "camera"]
    status: Literal["queued", "processing", "ready", "failed"]
    createdAt: datetime
    updatedAt: datetime
    startedAt: datetime | None
    completedAt: datetime | None
    currentStageKey: str | None
    progress: ProgressResponse
    notes: list[str]
    stages: list[StageResponse]
    pages: list[PageResponse]
    export: ExportResponse


class UpdatePageRequest(BaseModel):
    rotation: int | None = None
    deleted: bool | None = None


class BulkUpdatePagesRequest(BaseModel):
    pageIds: list[str]
    rotation: int | None = None
    deleted: bool | None = None


class ReorderPagesRequest(BaseModel):
    orderedPageIds: list[str]
