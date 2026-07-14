import queue
from typing import Iterator, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.settings import settings
from app.processing.ocr import get_available_languages
from app.schemas.job import (
    AddManualPageRequest,
    BulkUpdatePagesRequest,
    CreateJobFromUrlRequest,
    ExportResponse,
    JobResponse,
    OcrLanguagesResponse,
    ReorderPagesRequest,
    ReprocessJobRequest,
    UpdatePageRequest,
)
from app.services.job_service import JobNotCancellableError, job_service

router = APIRouter()


@router.get("/ocr/languages", response_model=OcrLanguagesResponse)
def list_ocr_languages() -> OcrLanguagesResponse:
    return OcrLanguagesResponse(
        languages=get_available_languages(),
        default=settings.ocr_language,
    )


@router.get("/events")
def stream_job_events() -> StreamingResponse:
    """Server-sent events: one `data:` line per job state change."""

    def event_stream() -> Iterator[str]:
        subscriber = job_service.subscribe()
        try:
            yield ": connected\n\n"
            while True:
                try:
                    # Queue items are complete SSE frames (job updates and
                    # named "deleted" events).
                    yield subscriber.get(timeout=15.0)
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            job_service.unsubscribe(subscriber)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs() -> list[JobResponse]:
    return job_service.list_jobs()


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _validate_trim(trim_start: float | None, trim_end: float | None) -> None:
    if trim_start is not None and trim_start < 0:
        raise HTTPException(status_code=422, detail="Trim start must be zero or positive.")
    if trim_end is not None and trim_end <= 0:
        raise HTTPException(status_code=422, detail="Trim end must be positive.")
    if trim_start is not None and trim_end is not None and trim_end <= trim_start:
        raise HTTPException(status_code=422, detail="Trim end must be after trim start.")


@router.post("/jobs/upload", response_model=JobResponse)
async def upload_job(
    file: UploadFile = File(...),
    processing_mode: Literal["screen", "camera"] = Form("screen"),
    ocr_language: str = Form("eng"),
    sensitivity: Literal["fewer", "balanced", "more"] = Form("balanced"),
    trim_start: float | None = Form(None),
    trim_end: float | None = Form(None),
) -> JobResponse:
    _validate_trim(trim_start, trim_end)
    return await job_service.create_job(
        file,
        processing_mode,
        ocr_language,
        sensitivity,
        trim_start=trim_start,
        trim_end=trim_end,
    )


@router.post("/jobs/from-url", response_model=JobResponse)
def create_job_from_url(payload: CreateJobFromUrlRequest) -> JobResponse:
    _validate_trim(payload.trimStart, payload.trimEnd)
    job = job_service.create_job_from_url(
        payload.url,
        processing_mode=payload.processingMode,
        ocr_language=payload.ocrLanguage,
        sensitivity=payload.sensitivity,
        trim_start=payload.trimStart,
        trim_end=payload.trimEnd,
    )
    if job is None:
        raise HTTPException(status_code=400, detail="Enter a valid http(s) video URL.")
    return job


@router.post("/jobs/{job_id}/reprocess", response_model=JobResponse)
def reprocess_job(job_id: str, payload: ReprocessJobRequest) -> JobResponse:
    _validate_trim(payload.trimStart, payload.trimEnd)
    job = job_service.reprocess_job(
        job_id,
        payload.sensitivity,
        trim_start=payload.trimStart,
        trim_end=payload.trimEnd,
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or has no stored video")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str) -> JobResponse:
    try:
        job = job_service.cancel_job(job_id)
    except JobNotCancellableError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str) -> None:
    if not job_service.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")


@router.post("/jobs/{job_id}/export", response_model=ExportResponse)
def export_job(job_id: str) -> ExportResponse:
    export_result = job_service.export_job(job_id)
    if export_result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return export_result


@router.post("/jobs/{job_id}/export/text", response_model=ExportResponse)
def export_text_job(job_id: str) -> ExportResponse:
    export_result = job_service.export_text_job(job_id)
    if export_result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return export_result


@router.post("/jobs/{job_id}/export/searchable", response_model=ExportResponse)
def export_searchable_job(job_id: str) -> ExportResponse:
    export_result = job_service.export_searchable_job(job_id)
    if export_result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return export_result


@router.patch("/jobs/{job_id}/pages/{page_id}", response_model=JobResponse)
def update_page(job_id: str, page_id: str, payload: UpdatePageRequest) -> JobResponse:
    job = job_service.update_page(job_id, page_id, payload)
    if job is None:
        raise HTTPException(status_code=404, detail="Job or page not found")
    return job


@router.patch("/jobs/{job_id}/pages", response_model=JobResponse)
def bulk_update_pages(job_id: str, payload: BulkUpdatePagesRequest) -> JobResponse:
    job = job_service.bulk_update_pages(job_id, payload)
    if job is None:
        raise HTTPException(status_code=404, detail="Job or pages not found")
    return job


@router.post("/jobs/{job_id}/pages/manual", response_model=JobResponse)
def add_manual_page(job_id: str, payload: AddManualPageRequest) -> JobResponse:
    job = job_service.add_manual_page(job_id, payload)
    if job is None:
        raise HTTPException(status_code=400, detail="Could not add a page from the requested video frame")
    return job


@router.post("/jobs/{job_id}/rejected/{rejected_id}/restore", response_model=JobResponse)
def restore_rejected_frame(job_id: str, rejected_id: str) -> JobResponse:
    job = job_service.restore_rejected_frame(job_id, rejected_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job or rejected page not found")
    return job


@router.post("/jobs/{job_id}/pages/reorder", response_model=JobResponse)
def reorder_pages(job_id: str, payload: ReorderPagesRequest) -> JobResponse:
    job = job_service.reorder_pages(job_id, payload)
    if job is None:
        raise HTTPException(status_code=400, detail="Invalid page order or job not found")
    return job
