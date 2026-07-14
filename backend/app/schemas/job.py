from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class EditPointPayload(BaseModel):
    x: float
    y: float


class CropBoxPayload(BaseModel):
    x: int
    y: int
    width: int
    height: int


class DrawStrokePayload(BaseModel):
    color: str
    width: int
    points: list[EditPointPayload]


class TextAnnotationPayload(BaseModel):
    text: str
    x: float
    y: float
    color: str
    fontSize: int


class BlurRegionPayload(BaseModel):
    x: int
    y: int
    width: int
    height: int
    intensity: int


PageFilterLiteral = Literal["none", "enhance", "grayscale", "bw"]


class PageEditsPayload(BaseModel):
    rotation: int
    crop: CropBoxPayload | None
    filter: PageFilterLiteral = "none"
    strokes: list[DrawStrokePayload]
    texts: list[TextAnnotationPayload]
    blurRegions: list[BlurRegionPayload]


class UpdatePageEditsPayload(BaseModel):
    rotation: int = 0
    crop: CropBoxPayload | None = None
    filter: PageFilterLiteral = "none"
    strokes: list[DrawStrokePayload] = []
    texts: list[TextAnnotationPayload] = []
    blurRegions: list[BlurRegionPayload] = []


class OcrBlockPayload(BaseModel):
    text: str
    confidence: float
    top: int
    left: int


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
    sourceImageUrl: str | None
    sharpnessScore: float
    segmentStart: float
    segmentEnd: float
    sourceFrameIndex: int
    sourceTimestamp: float
    manual: bool
    rotation: int
    status: Literal["active", "deleted"]
    deleted: bool
    edits: PageEditsPayload
    ocrText: str | None = None
    ocrBlocks: list[OcrBlockPayload] = []
    ocrStatus: Literal["pending", "ready", "failed", "empty"] = "pending"
    ocrError: str | None = None


class ExportResponse(BaseModel):
    status: Literal["idle", "processing", "ready", "failed"]
    progressPercent: int
    filename: str | None
    downloadUrl: str | None
    texUrl: str | None = None
    requestedAt: datetime | None
    completedAt: datetime | None
    error: str | None


class JobResponse(BaseModel):
    id: str
    filename: str
    processingMode: Literal["screen", "camera"]
    sourceVideoUrl: str | None
    sourceUrl: str | None = None
    ocrLanguage: str = "eng"
    sensitivity: Literal["fewer", "balanced", "more"] = "balanced"
    status: Literal["queued", "processing", "ready", "failed", "cancelled"]
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
    textExport: ExportResponse
    searchableExport: ExportResponse


class UpdatePageRequest(BaseModel):
    rotation: int | None = None
    deleted: bool | None = None
    edits: UpdatePageEditsPayload | None = None


class BulkUpdatePagesRequest(BaseModel):
    pageIds: list[str]
    rotation: int | None = None
    deleted: bool | None = None


class AddManualPageRequest(BaseModel):
    timestampSeconds: float


class ReorderPagesRequest(BaseModel):
    orderedPageIds: list[str]


class CreateJobFromUrlRequest(BaseModel):
    url: str
    processingMode: Literal["screen", "camera"] = "screen"
    ocrLanguage: str = "eng"
    sensitivity: Literal["fewer", "balanced", "more"] = "balanced"


class ReprocessJobRequest(BaseModel):
    sensitivity: Literal["fewer", "balanced", "more"] | None = None


class OcrLanguagesResponse(BaseModel):
    languages: list[str]
    default: str
