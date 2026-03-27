from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from fastapi import UploadFile

from app.core.settings import settings
from app.models.job import ExportArtifact, Job, Page, ProcessingMode, Progress, Stage
from app.processing.context import build_pipeline_context
from app.processing.deduper import remove_duplicates
from app.processing.debug import write_pipeline_debug_report
from app.processing.pipeline import PIPELINE_STAGES, build_export
from app.processing.preview import attach_previews
from app.processing.sampler import load_video_metadata, sample_frames
from app.processing.sequence import collapse_sequence_candidates
from app.processing.segmenter import detect_stable_segments
from app.processing.selector import select_best_frames
from app.processing.types import FrameQuality, SampledFrame, SelectedPage
from app.schemas.job import (
    BulkUpdatePagesRequest,
    ExportResponse,
    JobResponse,
    PageResponse,
    ProgressResponse,
    ReorderPagesRequest,
    StageResponse,
    UpdatePageRequest,
)


class JobService:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vid2pdf-worker")
        self._storage_root = Path(settings.storage_path)
        self._uploads_root = self._storage_root / "uploads"
        self._exports_root = self._storage_root / "exports"
        self._jobs_root = self._storage_root / "jobs"
        self._state_path = self._storage_root / "jobs_state.json"
        self._uploads_root.mkdir(parents=True, exist_ok=True)
        self._exports_root.mkdir(parents=True, exist_ok=True)
        self._jobs_root.mkdir(parents=True, exist_ok=True)
        self._load_jobs()
        self._recover_interrupted_jobs()

    def list_jobs(self) -> list[JobResponse]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
            return [self._to_response(job) for job in jobs]

    def get_job(self, job_id: str) -> JobResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return None if job is None else self._to_response(job)

    async def create_job(
        self,
        file: UploadFile,
        processing_mode: ProcessingMode = "screen",
    ) -> JobResponse:
        job_id = uuid4().hex[:12]
        created_at = datetime.now(timezone.utc)
        upload_path = self._uploads_root / f"{job_id}-{file.filename or 'upload.bin'}"
        upload_path.write_bytes(await file.read())

        stages = [Stage(key=key, label=label, status="pending") for key, label in PIPELINE_STAGES]
        job = Job(
            id=job_id,
            filename=file.filename or "uploaded-video",
            processing_mode=processing_mode,
            status="queued",
            created_at=created_at,
            updated_at=created_at,
            progress=Progress(percent=2, message="Upload received. Waiting for background worker."),
            notes=[
                "Job created and queued for background reconstruction.",
                "Review actions persist through the backend once pages are ready.",
            ],
            stages=stages,
            upload_path=str(upload_path),
        )

        with self._lock:
            self._jobs[job_id] = job
            self._save_jobs()

        self._executor.submit(self._run_pipeline_job, job_id)
        return self._to_response(job)

    def update_page(self, job_id: str, page_id: str, payload: UpdatePageRequest) -> JobResponse | None:
        with self._lock:
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
            self._save_jobs()
            return self._to_response(job)

    def bulk_update_pages(
        self,
        job_id: str,
        payload: BulkUpdatePagesRequest,
    ) -> JobResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            page_by_id = {page.id: page for page in job.pages}
            if any(page_id not in page_by_id for page_id in payload.pageIds):
                return None

            for page_id in payload.pageIds:
                page = page_by_id[page_id]
                if payload.rotation is not None:
                    page.rotation = payload.rotation % 360
                if payload.deleted is not None:
                    page.deleted = payload.deleted
                    page.status = "deleted" if payload.deleted else "active"

            self._invalidate_export(job)
            job.updated_at = datetime.now(timezone.utc)
            self._save_jobs()
            return self._to_response(job)

    def reorder_pages(self, job_id: str, payload: ReorderPagesRequest) -> JobResponse | None:
        with self._lock:
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
            self._save_jobs()
            return self._to_response(job)

    def export_job(self, job_id: str) -> ExportResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            if job.export.status == "processing":
                return self._to_export_response(job.export)

            now = datetime.now(timezone.utc)
            job.export = ExportArtifact(
                status="processing",
                progress_percent=5,
                requested_at=now,
            )
            job.updated_at = now
            self._save_jobs()

        self._executor.submit(self._run_export_job, job_id)
        return self._to_export_response(job.export)

    def _run_pipeline_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "processing"
            job.started_at = datetime.now(timezone.utc)
            job.updated_at = job.started_at
            job.progress = Progress(percent=5, message="Preparing video analysis.")
            self._save_jobs()

        try:
            with self._lock:
                job = self._jobs[job_id]
                upload_path = job.upload_path
                processing_mode = job.processing_mode
            if not upload_path:
                raise ValueError("Uploaded video path is missing.")

            context = build_pipeline_context(
                job_id=job_id,
                upload_path=upload_path,
                processing_mode=processing_mode,
            )
            mode_settings = self._pipeline_settings(processing_mode)

            self._start_stage(job_id, "sample_frames", "Sampling frames from the uploaded video.", 8)
            metadata = load_video_metadata(upload_path)
            sampled_frames = sample_frames(
                context=context,
                metadata=metadata,
                sample_fps=mode_settings["sample_fps"],
            )
            self._complete_stage(job_id, "sample_frames", 24, f"Sampled {len(sampled_frames)} frames.")

            self._start_stage(job_id, "detect_segments", "Detecting stable page-view segments.", 28)
            segments = detect_stable_segments(
                frames=sampled_frames,
                min_seconds=mode_settings["min_seconds"],
                max_change_ratio=mode_settings["max_change_ratio"],
                hash_distance_threshold=mode_settings["hash_distance_threshold"],
                mean_diff_threshold=mode_settings["mean_diff_threshold"],
            )
            self._complete_stage(job_id, "detect_segments", 46, f"Detected {len(segments)} stable segments.")

            self._start_stage(job_id, "select_frames", "Selecting the strongest frame from each segment.", 50)
            selected_pages = select_best_frames(segments, processing_mode=processing_mode)
            sequence_pages = collapse_sequence_candidates(selected_pages)
            self._complete_stage(
                job_id,
                "select_frames",
                66,
                f"Selected {len(selected_pages)} representative frames and collapsed them to {len(sequence_pages)} sequence-stable candidates.",
            )

            self._start_stage(job_id, "remove_duplicates", "Filtering duplicate or weak pages.", 70)
            unique_pages = remove_duplicates(
                sequence_pages,
                max_hamming_distance=mode_settings["dedupe_threshold"],
            )
            if not unique_pages and sequence_pages:
                unique_pages = [sequence_pages[0]]
            self._complete_stage(
                job_id,
                "remove_duplicates",
                82,
                f"Kept {len(unique_pages)} pages after deduplication.",
            )

            self._start_stage(job_id, "prepare_previews", "Writing page previews and final page images.", 86)
            preview_pages = attach_previews(unique_pages, context=context)
            self._complete_stage(job_id, "prepare_previews", 96, "Preview artifacts written.")
            write_pipeline_debug_report(
                context=context,
                sampled_frames=sampled_frames,
                segments=segments,
                selected_pages=selected_pages,
                sequence_pages=sequence_pages,
                deduped_pages=preview_pages,
            )

            with self._lock:
                job = self._jobs[job_id]
                job.notes = [
                    f"Pipeline completed in {processing_mode} mode with background execution.",
                    "Pages can now be reviewed, reordered, rotated, deleted, and exported through backend-backed state.",
                    f"Processed video at {metadata.fps:.2f} fps, {metadata.width}x{metadata.height}, duration {metadata.duration_seconds:.1f}s.",
                    f"Sampled {len(sampled_frames)} frames and detected {len(segments)} stable page segments.",
                    f"Selected {len(selected_pages)} representative frames, collapsed to {len(sequence_pages)} sequence-stable candidates, removed {len(sequence_pages) - len(preview_pages)} duplicates, and kept {len(preview_pages)} pages after deduplication.",
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
                    for index, page in enumerate(preview_pages)
                ]
                for selected_page in preview_pages:
                    for note in selected_page.notes:
                        job.notes.append(f"{selected_page.label}: {note}")

                job.status = "ready"
                job.completed_at = datetime.now(timezone.utc)
                job.current_stage_key = job.stages[-1].key if job.stages else None
                job.progress = Progress(percent=100, message="Pages are ready for review.")
                job.updated_at = job.completed_at
                self._save_jobs()
        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.status = "failed"
                job.progress = Progress(percent=100, message="Pipeline failed.")
                job.updated_at = datetime.now(timezone.utc)
                job.notes.append(f"Pipeline error: {exc}")
                current_stage = next(
                    (stage for stage in job.stages if stage.status == "processing"),
                    None,
                )
                if current_stage is not None:
                    current_stage.status = "failed"
                self._save_jobs()

    def _run_export_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            active_pages = [
                page for page in sorted(job.pages, key=lambda item: item.order_index) if not page.deleted
            ]
            if not active_pages:
                job.export.status = "failed"
                job.export.error = "No active pages available for export."
                job.updated_at = datetime.now(timezone.utc)
                self._save_jobs()
                return
            selected_pages = [self._to_selected_page(page) for page in active_pages]
            job.export.progress_percent = 35
            self._save_jobs()

        try:
            artifact = build_export(
                job_id=job_id,
                pages=selected_pages,
                output_dir=str(self._exports_root),
            )
        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.export.status = "failed"
                job.export.progress_percent = 100
                job.export.error = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                self._save_jobs()
            return

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.export.status = "ready"
            job.export.progress_percent = 100
            job.export.filename = artifact.filename
            job.export.download_url = f"{settings.public_artifact_base_url}/exports/{artifact.filename}"
            job.export.completed_at = datetime.now(timezone.utc)
            job.export.error = None
            job.updated_at = job.export.completed_at
            self._save_jobs()

    def _start_stage(self, job_id: str, stage_key: str, message: str, progress_percent: int) -> None:
        with self._lock:
            job = self._jobs[job_id]
            now = datetime.now(timezone.utc)
            for stage in job.stages:
                if stage.key == stage_key:
                    stage.status = "processing"
                    stage.started_at = stage.started_at or now
                    stage.progress_percent = max(stage.progress_percent, 5)
                elif stage.status not in {"complete", "failed"}:
                    stage.status = "pending"
                    stage.progress_percent = 0
            job.current_stage_key = stage_key
            job.progress = Progress(percent=progress_percent, message=message)
            job.updated_at = now
            self._save_jobs()

    def _complete_stage(
        self,
        job_id: str,
        stage_key: str,
        progress_percent: int,
        message: str,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            stage = next((item for item in job.stages if item.key == stage_key), None)
            if stage is None:
                return
            now = datetime.now(timezone.utc)
            stage.status = "complete"
            stage.progress_percent = 100
            stage.completed_at = now
            job.progress = Progress(percent=progress_percent, message=message)
            job.updated_at = now
            self._save_jobs()

    def _pipeline_settings(self, processing_mode: ProcessingMode) -> dict[str, float | int]:
        if processing_mode == "camera":
            return {
                "sample_fps": settings.camera_sample_fps,
                "min_seconds": settings.camera_stable_segment_min_seconds,
                "max_change_ratio": settings.camera_stable_segment_max_change_ratio,
                "hash_distance_threshold": settings.camera_stable_segment_hash_distance_threshold,
                "mean_diff_threshold": settings.camera_stable_segment_mean_diff_threshold,
                "dedupe_threshold": settings.camera_dedupe_max_hash_distance,
            }
        return {
            "sample_fps": settings.screen_sample_fps,
            "min_seconds": settings.screen_stable_segment_min_seconds,
            "max_change_ratio": settings.screen_stable_segment_max_change_ratio,
            "hash_distance_threshold": settings.screen_stable_segment_hash_distance_threshold,
            "mean_diff_threshold": settings.screen_stable_segment_mean_diff_threshold,
            "dedupe_threshold": settings.screen_dedupe_max_hash_distance,
        }

    def _recover_interrupted_jobs(self) -> None:
        with self._lock:
            changed = False
            for job in self._jobs.values():
                if job.status in {"queued", "processing"}:
                    job.status = "failed"
                    job.progress = Progress(percent=100, message="Processing interrupted by server restart.")
                    job.notes.append("Job was interrupted before completion and needs to be re-uploaded.")
                    for stage in job.stages:
                        if stage.status == "processing":
                            stage.status = "failed"
                    changed = True
                if job.export.status == "processing":
                    job.export.status = "failed"
                    job.export.error = "Export interrupted by server restart."
                    changed = True
            if changed:
                self._save_jobs()

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
            page_coverage=1.0,
            rectangularity=1.0,
            occlusion_ratio=0.0,
            transition_penalty=0.0,
            readability_score=page.sharpness_score,
            sharpness_score=page.sharpness_score,
            contrast_score=0.0,
            brightness_score=0.0,
            text_density=0.0,
            single_page_score=1.0,
            background_intrusion_ratio=0.0,
            border_touch_ratio=0.0,
            contour_confidence=1.0,
            gutter_ratio=0.0,
            opposing_page_ratio=0.0,
            stability_score=1.0,
            rejected=False,
            rejection_reasons=[],
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
            processingMode=job.processing_mode,
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

    def _save_jobs(self) -> None:
        payload = {"jobs": [self._serialize_job(job) for job in self._jobs.values()]}
        self._state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_jobs(self) -> None:
        if not self._state_path.exists():
            return

        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return

        jobs = payload.get("jobs", [])
        for item in jobs:
            job = self._deserialize_job(item)
            self._jobs[job.id] = job

    def _serialize_job(self, job: Job) -> dict[str, object]:
        return {
            "id": job.id,
            "filename": job.filename,
            "processing_mode": job.processing_mode,
            "status": job.status,
            "created_at": self._serialize_datetime(job.created_at),
            "updated_at": self._serialize_datetime(job.updated_at),
            "started_at": self._serialize_datetime(job.started_at),
            "completed_at": self._serialize_datetime(job.completed_at),
            "current_stage_key": job.current_stage_key,
            "progress": {
                "percent": job.progress.percent,
                "message": job.progress.message,
            },
            "notes": job.notes,
            "stages": [
                {
                    "key": stage.key,
                    "label": stage.label,
                    "status": stage.status,
                    "progress_percent": stage.progress_percent,
                    "started_at": self._serialize_datetime(stage.started_at),
                    "completed_at": self._serialize_datetime(stage.completed_at),
                }
                for stage in job.stages
            ],
            "pages": [
                {
                    "id": page.id,
                    "job_id": page.job_id,
                    "order_index": page.order_index,
                    "page_number": page.page_number,
                    "preview_label": page.preview_label,
                    "thumbnail_url": page.thumbnail_url,
                    "image_url": page.image_url,
                    "sharpness_score": page.sharpness_score,
                    "segment_start": page.segment_start,
                    "segment_end": page.segment_end,
                    "source_frame_index": page.source_frame_index,
                    "source_timestamp": page.source_timestamp,
                    "rotation": page.rotation,
                    "status": page.status,
                    "deleted": page.deleted,
                }
                for page in job.pages
            ],
            "export": {
                "status": job.export.status,
                "progress_percent": job.export.progress_percent,
                "filename": job.export.filename,
                "download_url": job.export.download_url,
                "requested_at": self._serialize_datetime(job.export.requested_at),
                "completed_at": self._serialize_datetime(job.export.completed_at),
                "error": job.export.error,
            },
            "upload_path": job.upload_path,
        }

    def _deserialize_job(self, payload: dict[str, object]) -> Job:
        progress_payload = payload.get("progress", {})
        export_payload = payload.get("export", {})
        return Job(
            id=str(payload["id"]),
            filename=str(payload["filename"]),
            processing_mode=payload["processing_mode"],  # type: ignore[arg-type]
            status=payload["status"],  # type: ignore[arg-type]
            created_at=self._deserialize_datetime(payload.get("created_at")),
            updated_at=self._deserialize_datetime(payload.get("updated_at")),
            started_at=self._deserialize_datetime(payload.get("started_at")),
            completed_at=self._deserialize_datetime(payload.get("completed_at")),
            current_stage_key=payload.get("current_stage_key"),  # type: ignore[arg-type]
            progress=Progress(
                percent=int(progress_payload.get("percent", 0)),  # type: ignore[union-attr]
                message=str(progress_payload.get("message", "Waiting to start.")),  # type: ignore[union-attr]
            ),
            notes=[str(note) for note in payload.get("notes", [])],  # type: ignore[arg-type]
            stages=[
                Stage(
                    key=str(stage["key"]),
                    label=str(stage["label"]),
                    status=stage["status"],  # type: ignore[arg-type]
                    progress_percent=int(stage.get("progress_percent", 0)),
                    started_at=self._deserialize_datetime(stage.get("started_at")),
                    completed_at=self._deserialize_datetime(stage.get("completed_at")),
                )
                for stage in payload.get("stages", [])  # type: ignore[arg-type]
            ],
            pages=[
                Page(
                    id=str(page["id"]),
                    job_id=str(page["job_id"]),
                    order_index=int(page["order_index"]),
                    page_number=int(page["page_number"]),
                    preview_label=str(page["preview_label"]),
                    thumbnail_url=page.get("thumbnail_url"),  # type: ignore[arg-type]
                    image_url=page.get("image_url"),  # type: ignore[arg-type]
                    sharpness_score=float(page["sharpness_score"]),
                    segment_start=float(page["segment_start"]),
                    segment_end=float(page["segment_end"]),
                    source_frame_index=int(page["source_frame_index"]),
                    source_timestamp=float(page["source_timestamp"]),
                    rotation=int(page.get("rotation", 0)),
                    status=page.get("status", "active"),  # type: ignore[arg-type]
                    deleted=bool(page.get("deleted", False)),
                )
                for page in payload.get("pages", [])  # type: ignore[arg-type]
            ],
            export=ExportArtifact(
                status=export_payload.get("status", "idle"),  # type: ignore[arg-type]
                progress_percent=int(export_payload.get("progress_percent", 0)),  # type: ignore[union-attr]
                filename=export_payload.get("filename"),  # type: ignore[arg-type]
                download_url=export_payload.get("download_url"),  # type: ignore[arg-type]
                requested_at=self._deserialize_datetime(export_payload.get("requested_at")),  # type: ignore[union-attr]
                completed_at=self._deserialize_datetime(export_payload.get("completed_at")),  # type: ignore[union-attr]
                error=export_payload.get("error"),  # type: ignore[arg-type]
            ),
            upload_path=payload.get("upload_path"),  # type: ignore[arg-type]
        )

    def _serialize_datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    def _deserialize_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(str(value))


job_service = JobService()
