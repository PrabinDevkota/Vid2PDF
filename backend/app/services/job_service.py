from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.settings import settings
from app.models.job import ExportArtifact, Job, Page, Progress, Stage
from app.processing.pipeline import PIPELINE_STAGES, build_export, run_reconstruction_pipeline
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
EXPORT_DURATION_SECONDS = 2.0


class JobService:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._storage_root = Path(settings.storage_path)
        self._uploads_root = self._storage_root / "uploads"
        self._exports_root = self._storage_root / "exports"
        self._uploads_root.mkdir(parents=True, exist_ok=True)
        self._exports_root.mkdir(parents=True, exist_ok=True)

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
        job.updated_at = datetime.now(timezone.utc)
        return self._to_response(job)

    def export_job(self, job_id: str) -> ExportResponse | None:
        self._sync_jobs()
        job = self._jobs.get(job_id)
        if job is None:
            return None

        now = datetime.now(timezone.utc)
        if job.export.status in {"idle", "failed"}:
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
            self._materialize_pipeline_output(job)
            for index, stage in enumerate(job.stages):
                stage.status = "complete"
                stage.progress_percent = 100
                if stage.started_at is None:
                    stage.started_at = job.started_at + timedelta(seconds=index * STAGE_DURATION_SECONDS)
                if stage.completed_at is None:
                    stage.completed_at = stage.started_at + timedelta(seconds=STAGE_DURATION_SECONDS)

            job.status = "ready"
            job.completed_at = job.started_at + timedelta(seconds=len(job.stages) * STAGE_DURATION_SECONDS)
            job.current_stage_key = job.stages[-1].key
            job.progress = Progress(percent=100, message="Pages are ready for review.")

        self._sync_export(job)

    def _materialize_pipeline_output(self, job: Job) -> None:
        if job.pages:
            return

        pipeline_result = run_reconstruction_pipeline(filename=job.filename)
        job.notes = [
            "Pipeline completed with placeholder extraction logic behind real job and page contracts.",
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
                thumbnail_url=self._build_page_data_url(job.filename, index + 1, page.selected_frame.sharpness_score),
                image_url=self._build_page_data_url(job.filename, index + 1, page.selected_frame.sharpness_score),
                sharpness_score=page.selected_frame.sharpness_score,
                segment_start=max(0.0, page.selected_frame.timestamp - 0.3),
                segment_end=page.selected_frame.timestamp + 1.0,
                source_frame_index=page.selected_frame.frame_index,
                source_timestamp=page.selected_frame.timestamp,
            )
            for index, page in enumerate(pipeline_result.pages)
        ]

    def _sync_export(self, job: Job) -> None:
        export = job.export
        if export.status != "processing" or export.requested_at is None:
            return

        elapsed = (datetime.now(timezone.utc) - export.requested_at).total_seconds()
        export.progress_percent = max(10, min(94, int((elapsed / EXPORT_DURATION_SECONDS) * 100)))
        if elapsed < EXPORT_DURATION_SECONDS:
            return

        active_pages = [page for page in sorted(job.pages, key=lambda item: item.order_index) if not page.deleted]
        artifact = build_export(
            job_id=job.id,
            pages=run_reconstruction_pipeline(job.filename).pages[: len(active_pages)],
        )
        file_path = self._exports_root / artifact.filename
        file_path.write_bytes(self._build_minimal_pdf(job.filename, active_pages))

        export.status = "ready"
        export.progress_percent = 100
        export.filename = artifact.filename
        export.download_url = f"{settings.public_artifact_base_url}/{artifact.filename}"
        export.completed_at = datetime.now(timezone.utc)
        export.error = None
        job.updated_at = export.completed_at

    def _build_page_data_url(self, filename: str, page_number: int, score: float) -> str:
        safe_title = self._escape_svg(filename)
        svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1200" viewBox="0 0 900 1200">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#eef4ff"/>
      <stop offset="100%" stop-color="#ffffff"/>
    </linearGradient>
  </defs>
  <rect width="900" height="1200" rx="44" fill="url(#bg)"/>
  <rect x="78" y="88" width="744" height="1024" rx="28" fill="#ffffff" stroke="#d9e2f0"/>
  <text x="128" y="180" fill="#173f8a" font-size="34" font-family="Arial, sans-serif">Vid2PDF Preview</text>
  <text x="128" y="236" fill="#10213b" font-size="50" font-weight="700" font-family="Arial, sans-serif">Page {page_number}</text>
  <text x="128" y="292" fill="#5d6b82" font-size="24" font-family="Arial, sans-serif">{safe_title}</text>
  <text x="128" y="372" fill="#10213b" font-size="26" font-family="Arial, sans-serif">Sharpness score</text>
  <text x="128" y="418" fill="#173f8a" font-size="40" font-weight="700" font-family="Arial, sans-serif">{score:.2f}</text>
  <rect x="128" y="478" width="520" height="16" rx="8" fill="#e8f0ff"/>
  <rect x="128" y="478" width="{max(120, int(score * 520))}" height="16" rx="8" fill="#173f8a"/>
  <rect x="128" y="560" width="562" height="20" rx="10" fill="#eff3f8"/>
  <rect x="128" y="610" width="602" height="20" rx="10" fill="#eff3f8"/>
  <rect x="128" y="660" width="546" height="20" rx="10" fill="#eff3f8"/>
  <rect x="128" y="710" width="500" height="20" rx="10" fill="#eff3f8"/>
</svg>
""".strip()
        encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"

    def _build_minimal_pdf(self, filename: str, active_pages: list[Page]) -> bytes:
        summary = [
            "BT",
            "/F1 18 Tf",
            "72 740 Td",
            f"({self._escape_pdf(filename)} - export summary) Tj",
            "0 -28 Td",
            f"({len(active_pages)} active pages exported) Tj",
        ]
        for index, page in enumerate(active_pages, start=1):
            summary.extend(
                [
                    "0 -24 Td",
                    f"(Page {index}: score {page.sharpness_score:.2f}, rotation {page.rotation}) Tj",
                ]
            )
        summary.append("ET")
        stream = "\n".join(summary)
        objects = [
            "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
            "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
            "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
            f"4 0 obj << /Length {len(stream.encode('utf-8'))} >> stream\n{stream}\nendstream\nendobj\n",
            "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        ]

        buffer = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(len(buffer))
            buffer.extend(obj.encode("utf-8"))

        xref_position = len(buffer)
        buffer.extend(f"xref\n0 {len(offsets)}\n".encode("utf-8"))
        buffer.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            buffer.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
        buffer.extend(
            (
                f"trailer << /Root 1 0 R /Size {len(offsets)} >>\n"
                f"startxref\n{xref_position}\n%%EOF"
            ).encode("utf-8")
        )
        return bytes(buffer)

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

    def _escape_svg(self, value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _escape_pdf(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


job_service = JobService()
