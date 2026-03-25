from datetime import datetime, timezone
from uuid import uuid4

from fastapi import UploadFile

from app.models.job import Job, Page, Stage
from app.processing.pipeline import PIPELINE_STAGES, build_export, run_reconstruction_pipeline
from app.schemas.job import ExportResponse, JobResponse, PageResponse, StageResponse


class JobService:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def list_jobs(self) -> list[JobResponse]:
        return [self._to_response(job) for job in self._jobs.values()]

    def get_job(self, job_id: str) -> JobResponse | None:
        job = self._jobs.get(job_id)
        return None if job is None else self._to_response(job)

    async def create_job(self, file: UploadFile) -> JobResponse:
        job_id = uuid4().hex[:12]
        stages = [Stage(key=key, label=label, state="pending") for key, label in PIPELINE_STAGES]

        job = Job(
            id=job_id,
            filename=file.filename or "uploaded-video",
            status="processing",
            created_at=datetime.now(timezone.utc),
            stages=stages,
        )
        self._jobs[job_id] = job

        pipeline_result = run_reconstruction_pipeline(filename=job.filename)
        job.notes.extend(pipeline_result.notes)
        job.pages = [
            Page(
                id=page.page_id,
                page_number=page.page_number,
                preview_label=page.label,
                preview_url=page.preview_url,
                sharpness_score=page.selected_frame.sharpness_score,
                segment_start=page.selected_frame.timestamp,
                segment_end=page.selected_frame.timestamp + 1.0,
            )
            for page in pipeline_result.pages
        ]
        job.stages = [Stage(key=stage.key, label=stage.label, state="complete") for stage in job.stages]
        job.status = "ready"

        return self._to_response(job)

    def export_job(self, job_id: str) -> ExportResponse | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None

        selected_pages = run_reconstruction_pipeline(job.filename).pages
        artifact = build_export(job_id=job_id, pages=selected_pages)
        return ExportResponse(
            filename=artifact.filename,
            downloadUrl=artifact.download_url,
            pageCount=artifact.page_count,
        )

    def _to_response(self, job: Job) -> JobResponse:
        return JobResponse(
            id=job.id,
            filename=job.filename,
            status=job.status,
            createdAt=job.created_at,
            notes=job.notes,
            stages=[
                StageResponse(key=stage.key, label=stage.label, state=stage.state)
                for stage in job.stages
            ],
            pages=[
                PageResponse(
                    id=page.id,
                    pageNumber=page.page_number,
                    previewLabel=page.preview_label,
                    previewUrl=page.preview_url,
                    sharpnessScore=page.sharpness_score,
                    segmentStart=page.segment_start,
                    segmentEnd=page.segment_end,
                    rotation=page.rotation,
                )
                for page in job.pages
            ],
        )


job_service = JobService()
