from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    opacity: float = Field(default=1.0, ge=0.05, le=1.0)


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
    mode: Literal["blur", "fill"] = "blur"
    fillColor: str = "#000000"


PageFilterLiteral = Literal["none", "enhance", "grayscale", "bw"]


class PageEditsPayload(BaseModel):
    rotation: int
    fineRotation: float = Field(default=0.0, ge=-15.0, le=15.0)
    crop: CropBoxPayload | None
    filter: PageFilterLiteral = "none"
    brightness: int = Field(default=0, ge=-100, le=100)
    contrast: int = Field(default=0, ge=-100, le=100)
    strokes: list[DrawStrokePayload]
    texts: list[TextAnnotationPayload]
    blurRegions: list[BlurRegionPayload]


class UpdatePageEditsPayload(BaseModel):
    rotation: int = 0
    fineRotation: float = Field(default=0.0, ge=-15.0, le=15.0)
    crop: CropBoxPayload | None = None
    filter: PageFilterLiteral = "none"
    brightness: int = Field(default=0, ge=-100, le=100)
    contrast: int = Field(default=0, ge=-100, le=100)
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
    ocrConfidence: float | None = None


class RejectedFrameResponse(BaseModel):
    id: str
    timestamp: float
    sourceFrameIndex: int
    reason: str
    score: float
    imageUrl: str | None = None
    thumbnailUrl: str | None = None


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
    cameraOutput: Literal["cleaned", "color"] = "cleaned"
    trimStart: float | None = None
    trimEnd: float | None = None
    videoWidth: int | None = None
    videoHeight: int | None = None
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
    rejectedFrames: list[RejectedFrameResponse] = []
    export: ExportResponse
    textExport: ExportResponse
    searchableExport: ExportResponse


class UpdatePageRequest(BaseModel):
    rotation: int | None = None
    deleted: bool | None = None
    edits: UpdatePageEditsPayload | None = None
    # Manual OCR-text correction; replaces the extracted text for exports.
    ocrText: str | None = None


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
    cameraOutput: Literal["cleaned", "color"] = "cleaned"
    trimStart: float | None = None
    trimEnd: float | None = None


class ReprocessJobRequest(BaseModel):
    sensitivity: Literal["fewer", "balanced", "more"] | None = None
    cameraOutput: Literal["cleaned", "color"] | None = None
    trimStart: float | None = None
    trimEnd: float | None = None


PageSizeLiteral = Literal["auto", "a4", "letter"]
MarginLiteral = Literal["none", "small"]


class ExportOptionsRequest(BaseModel):
    """Options for the image PDF export; defaults preserve prior behavior."""

    pageSize: PageSizeLiteral = "auto"
    margin: MarginLiteral = "none"


class MergedExportRequest(BaseModel):
    jobIds: list[str] = Field(min_length=1)
    pageSize: PageSizeLiteral = "auto"
    margin: MarginLiteral = "none"


class MergedExportResponse(BaseModel):
    filename: str
    downloadUrl: str
    pageCount: int
    jobCount: int


class SkewSuggestionResponse(BaseModel):
    """Auto-detected straightening angle; null when no tilt was found."""

    angle: float | None = None


class CropSuggestionResponse(BaseModel):
    """Auto-detected document crop for a page; crop is null when no region was found."""

    crop: CropBoxPayload | None = None


class OcrLanguagesResponse(BaseModel):
    languages: list[str]
    default: str
