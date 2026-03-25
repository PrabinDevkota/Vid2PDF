from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.settings import settings
from app.models.job import ExportArtifact, Job, Page, Progress, Stage
from app.processing.pipeline import PIPELINE_STAGES, build_export, run_reconstruction_pipeline
from app.processing.types import FrameQuality, SampledFrame, SelectedPage
from app.schemas.job import (
    ExportResponse,
    JobResponse,
    PageResponse,
    ProgressResponse,
    ReorderPagesRequest,
    StageResponse,
    UpdatePageRequest,
)

STAGE_DURATION_SECONDS = 1.2
EXPORT_DURATION_SECONDS = 1.2


class JobService:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._storage_root = Path(settings.storage_path)
        self._uploads_root = self._storage_root / "uploads"
        self._exports_root = self._storage_root / "exports"
        self._jobs_root = self._storage_root / "jobs"
        self._uploads_root.mkdir(parents=True, exist_ok=True)
        self._exports_root.mkdir(parents=True, exist_ok=True)
        self._jobs_root.mkdir(parents=True, exist_ok=True)

    def list_jobs(self) -> list[JobResponse]:
        self._sync_jobs()
        jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
        return [self._to_response(job) for job in jobs]

    def get_job(self, job_id: str) -> JobResponse | None:
        self._sync_jobs()
        job = self._jobs.get(job_id)
        return None if job is None else self._to_response(job)

    async def create_job(self, file: UploadFile) -> JobResponse:
        job_id = uuid4().hex[:12]
        created_at = datetime.now(timezone.utc)
        upload_path = self._uploads_root / f"{job_id}-{file.filename or 'upload.bin'}"
        upload_path.write_bytes(await file.read())

        stages = [
            Stage(key=key, label=label, status="pending")
            for key, label in PIPELINE_STAGES
        ]
        job = Job(
            id=job_id,
            filename=file.filename or "uploaded-video",
            status="queued",
            created_at=created_at,
            updated_at=created_at,
            notes=[
                "Job created and waiting for pipeline execution.",
                "Review actions persist through the backend once pages are ready.",
            ],
            stages=stages,
            upload_path=str(upload_path),
        )
        self._jobs[job_id] = job
        self._sync_job(job)
        return self._to_response(job)

    def update_page(self, job_id: str, page_id: str, payload: UpdatePageRequest) -> JobResponse | None:
        self._sync_jobs()
        job = self._jobs.get(job_id)
        if job is None:
            return None

        page = next((page for page in job.pages if page.id == page_id), None)
        if page is None:
            return None

        if payload.rotation is not None:
            page.rotation = payload.rotation % 360
        if payload.deleted is not None:
            page.deleted = payload.deleted
            page.status = "deleted" if payload.deleted else "active"

        self._invalidate_export(job)
        job.updated_at = datetime.now(timezone.utc)
        return self._to_response(job)

    def reorder_pages(self, job_id: str, payload: ReorderPagesRequest) -> JobResponse | None:
        self._sync_jobs()
        job = self._jobs.get(job_id)
        if job is None:
            return None

        page_by_id = {page.id: page for page in job.pages}
        if set(payload.orderedPageIds) != set(page_by_id):
            return None

        reordered_pages = [page_by_id[page_id] for page_id in payload.orderedPageIds]
        for index, page in enumerate(reordered_pages):
            page.order_index = index
            page.page_number = index + 1
        job.pages = reordered_pages
        self._invalidate_export(job)
        job.updated_at = datetime.now(timezone.utc)
        return self._to_response(job)

    def export_job(self, job_id: str) -> ExportResponse | None:
        self._sync_jobs()
        job = self._jobs.get(job_id)
        if job is None:
            return None

        now = datetime.now(timezone.utc)
        job.export = ExportArtifact(
            status="processing",
            progress_percent=5,
            requested_at=now,
        )
        job.updated_at = now

        self._sync_export(job)
        return self._to_export_response(job.export)

    def _sync_jobs(self) -> None:
        for job in self._jobs.values():
            self._sync_job(job)

    def _sync_job(self, job: Job) -> None:
        now = datetime.now(timezone.utc)
        elapsed = (now - job.created_at).total_seconds()

        if job.status in {"ready", "failed"}:
            self._sync_export(job)
            return

        if elapsed < 0.3:
            job.status = "queued"
            job.progress = Progress(percent=3, message="Upload received. Queueing reconstruction.")
            job.current_stage_key = None
            job.updated_at = now
            self._sync_export(job)
            return

        job.status = "processing"
        if job.started_at is None:
            job.started_at = job.created_at + timedelta(seconds=0.3)

        stage_index = min(int((elapsed - 0.3) / STAGE_DURATION_SECONDS), len(job.stages) - 1)
        stage_progress_raw = ((elapsed - 0.3) % STAGE_DURATION_SECONDS) / STAGE_DURATION_SECONDS

        for index, stage in enumerate(job.stages):
            if index < stage_index:
                stage.status = "complete"
                stage.progress_percent = 100
                if stage.started_at is None:
                    stage.started_at = job.started_at + timedelta(seconds=index * STAGE_DURATION_SECONDS)
                if stage.completed_at is None:
                    stage.completed_at = stage.started_at + timedelta(seconds=STAGE_DURATION_SECONDS)
            elif index == stage_index:
                stage.status = "processing"
                stage.progress_percent = max(8, min(96, int(stage_progress_raw * 100)))
                if stage.started_at is None:
                    stage.started_at = job.started_at + timedelta(seconds=index * STAGE_DURATION_SECONDS)
                stage.completed_at = None
            else:
                stage.status = "pending"
                stage.progress_percent = 0
                stage.started_at = None
                stage.completed_at = None

        current_stage = job.stages[stage_index]
        job.current_stage_key = current_stage.key
        overall_percent = int(
            ((stage_index + (current_stage.progress_percent / 100)) / len(job.stages)) * 100
        )
        job.progress = Progress(
            percent=max(5, min(overall_percent, 98)),
            message=f"{current_stage.label} in progress.",
        )
        job.updated_at = now

        total_processing_time = 0.3 + (len(job.stages) * STAGE_DURATION_SECONDS)
        if elapsed >= total_processing_time:
            try:
                self._materialize_pipeline_output(job)
            except Exception as exc:
                job.status = "failed"
                job.progress = Progress(percent=100, message="Pipeline failed.")
                job.notes.append(f"Pipeline error: {exc}")
                job.updated_at = datetime.now(timezone.utc)
                self._sync_export(job)
                return

            for index, stage in enumerate(job.stages):
                stage.status = "complete"
                stage.progress_percent = 100
                if stage.started_at is None:
                    stage.started_at = job.started_at + timedelta(seconds=index * STAGE_DURATION_SECONDS)
                if stage.completed_at is None:
                    stage.completed_at = stage.started_at + timedelta(seconds=STAGE_DURATION_SECONDS)

            job.status = "ready"
            job.completed_at = datetime.now(timezone.utc)
            job.current_stage_key = job.stages[-1].key
            job.progress = Progress(percent=100, message="Pages are ready for review.")

        self._sync_export(job)

    def _materialize_pipeline_output(self, job: Job) -> None:
        if job.pages:
            return
        if not job.upload_path:
            raise ValueError("Uploaded video path is missing.")

        pipeline_result = run_reconstruction_pipeline(job_id=job.id, upload_path=job.upload_path)
        job.notes = [
            "Pipeline completed with real video sampling, stable segment detection, frame scoring, preview writing, and deduplication.",
            "Pages can now be reviewed, reordered, rotated, deleted, and exported through backend-backed state.",
            *pipeline_result.notes,
        ]
        job.pages = [
            Page(
                id=page.page_id,
                job_id=job.id,
                order_index=index,
                page_number=index + 1,
                preview_label=page.label,
                thumbnail_url=page.preview_url,
                image_url=page.image_url,
                sharpness_score=page.selected_frame.quality.score,
                segment_start=page.segment_start,
                segment_end=page.segment_end,
                source_frame_index=page.selected_frame.frame_index,
                source_timestamp=page.selected_frame.timestamp,
            )
            for index, page in enumerate(pipeline_result.pages)
        ]
        for selected_page in pipeline_result.pages:
            for note in selected_page.notes:
                job.notes.append(f"{selected_page.label}: {note}")

    def _sync_export(self, job: Job) -> None:
        export = job.export
        if export.status != "processing" or export.requested_at is None:
            return

        elapsed = (datetime.now(timezone.utc) - export.requested_at).total_seconds()
        export.progress_percent = max(10, min(94, int((elapsed / EXPORT_DURATION_SECONDS) * 100)))
        if elapsed < EXPORT_DURATION_SECONDS:
            return

        active_pages = [page for page in sorted(job.pages, key=lambda item: item.order_index) if not page.deleted]
        if not active_pages:
            export.status = "failed"
            export.error = "No active pages available for export."
            job.updated_at = datetime.now(timezone.utc)
            return

        selected_pages = [self._to_selected_page(page) for page in active_pages]
        print(
            f"[Vid2PDF export] job={job.id} active_pages={len(active_pages)} "
            f"page_ids={[page.id for page in active_pages]}"
        )
        artifact = build_export(
            job_id=job.id,
            pages=selected_pages,
            output_dir=str(self._exports_root),
        )

        export.status = "ready"
        export.progress_percent = 100
        export.filename = artifact.filename
        export.download_url = f"{settings.public_artifact_base_url}/exports/{artifact.filename}"
        export.completed_at = datetime.now(timezone.utc)
        export.error = None
        job.updated_at = export.completed_at

    def _to_selected_page(self, page: Page) -> SelectedPage:
        if not page.image_url or not page.thumbnail_url:
            raise ValueError("Page image artifacts are missing.")

        image_path = self._resolve_storage_path(page.image_url)
        thumbnail_path = self._resolve_storage_path(page.thumbnail_url)
        quality = FrameQuality(
            sharpness=page.sharpness_score,
            brightness=0.0,
            contrast=0.0,
            edge_density=0.0,
            score=page.sharpness_score,
            perceptual_hash="0",
        )
        sampled_frame = SampledFrame(
            timestamp=page.source_timestamp,
            frame_index=page.source_frame_index,
            image=None,  # type: ignore[arg-type]
            quality=quality,
        )
        return SelectedPage(
            page_id=page.id,
            page_number=page.page_number,
            label=page.preview_label,
            source_segment_id=f"export-{page.id}",
            segment_start=page.segment_start,
            segment_end=page.segment_end,
            selected_frame=sampled_frame,
            image_path=str(image_path),
            thumbnail_path=str(thumbnail_path),
            rotation=page.rotation,
            preview_url=page.thumbnail_url,
            image_url=page.image_url,
        )

    def _resolve_storage_path(self, artifact_url: str) -> Path:
        prefix = f"{settings.public_artifact_base_url}/"
        if not artifact_url.startswith(prefix):
            raise ValueError(f"Unexpected artifact URL: {artifact_url}")
        relative_path = artifact_url.removeprefix(prefix)
        return self._storage_root / relative_path

    def _to_response(self, job: Job) -> JobResponse:
        pages = sorted(job.pages, key=lambda page: page.order_index)
        return JobResponse(
            id=job.id,
            filename=job.filename,
            status=job.status,
            createdAt=job.created_at,
            updatedAt=job.updated_at,
            startedAt=job.started_at,
            completedAt=job.completed_at,
            currentStageKey=job.current_stage_key,
            progress=ProgressResponse(
                percent=job.progress.percent,
                message=job.progress.message,
            ),
            notes=job.notes,
            stages=[
                StageResponse(
                    key=stage.key,
                    label=stage.label,
                    status=stage.status,
                    progressPercent=stage.progress_percent,
                    startedAt=stage.started_at,
                    completedAt=stage.completed_at,
                )
                for stage in job.stages
            ],
            pages=[
                PageResponse(
                    id=page.id,
                    jobId=page.job_id,
                    orderIndex=page.order_index,
                    pageNumber=page.page_number,
                    previewLabel=page.preview_label,
                    thumbnailUrl=page.thumbnail_url,
                    imageUrl=page.image_url,
                    sharpnessScore=page.sharpness_score,
                    segmentStart=page.segment_start,
                    segmentEnd=page.segment_end,
                    sourceFrameIndex=page.source_frame_index,
                    sourceTimestamp=page.source_timestamp,
                    rotation=page.rotation,
                    status=page.status,
                    deleted=page.deleted,
                )
                for page in pages
            ],
            export=self._to_export_response(job.export),
        )

    def _to_export_response(self, export: ExportArtifact) -> ExportResponse:
        return ExportResponse(
            status=export.status,
            progressPercent=export.progress_percent,
            filename=export.filename,
            downloadUrl=export.download_url,
            requestedAt=export.requested_at,
            completedAt=export.completed_at,
            error=export.error,
        )

    def _invalidate_export(self, job: Job) -> None:
        job.export = ExportArtifact()


job_service = JobService()
