from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.job import ExportResponse, JobResponse
from app.services.job_service import job_service

router = APIRouter()


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
async def upload_job(file: UploadFile = File(...)) -> JobResponse:
    return await job_service.create_job(file)


@router.post("/jobs/{job_id}/export", response_model=ExportResponse)
def export_job(job_id: str) -> ExportResponse:
    export_result = job_service.export_job(job_id)
    if export_result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return export_result
