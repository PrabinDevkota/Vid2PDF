from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

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
from app.services.job_service import job_service

router = APIRouter()


@router.get("/ocr/languages", response_model=OcrLanguagesResponse)
def list_ocr_languages() -> OcrLanguagesResponse:
    return OcrLanguagesResponse(
        languages=get_available_languages(),
        default=settings.ocr_language,
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


@router.post("/jobs/upload", response_model=JobResponse)
async def upload_job(
    file: UploadFile = File(...),
    processing_mode: Literal["screen", "camera"] = Form("screen"),
    ocr_language: str = Form("eng"),
    sensitivity: Literal["fewer", "balanced", "more"] = Form("balanced"),
) -> JobResponse:
    return await job_service.create_job(file, processing_mode, ocr_language, sensitivity)


@router.post("/jobs/from-url", response_model=JobResponse)
def create_job_from_url(payload: CreateJobFromUrlRequest) -> JobResponse:
    job = job_service.create_job_from_url(
        payload.url,
        processing_mode=payload.processingMode,
        ocr_language=payload.ocrLanguage,
        sensitivity=payload.sensitivity,
    )
    if job is None:
        raise HTTPException(status_code=400, detail="Enter a valid http(s) video URL.")
    return job


@router.post("/jobs/{job_id}/reprocess", response_model=JobResponse)
def reprocess_job(job_id: str, payload: ReprocessJobRequest) -> JobResponse:
    job = job_service.reprocess_job(job_id, payload.sensitivity)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or has no stored video")
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


@router.post("/jobs/{job_id}/pages/reorder", response_model=JobResponse)
def reorder_pages(job_id: str, payload: ReorderPagesRequest) -> JobResponse:
    job = job_service.reorder_pages(job_id, payload)
    if job is None:
        raise HTTPException(status_code=400, detail="Invalid page order or job not found")
    return job
