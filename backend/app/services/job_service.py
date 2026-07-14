from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

import cv2
from fastapi import UploadFile

from app.core.settings import settings
from app.models.job import (
    BlurRegion,
    CropBox,
    DrawStroke,
    EditPoint,
    ExportArtifact,
    Job,
    OcrBlock,
    Page,
    PageEdits,
    ProcessingMode,
    Progress,
    Stage,
    TextAnnotation,
)
from app.processing.context import build_pipeline_context
from app.processing.deduper import remove_duplicates
from app.processing.debug import write_pipeline_debug_report
from app.processing.document import detect_document_region
from app.processing.downloader import download_video, is_valid_video_url
from app.processing.editor import write_rendered_page
from app.processing.ocr import (
    PageText,
    TextBlock,
    extract_page_text,
    extract_pages_text_parallel,
    sanitize_language,
)
from app.processing.pipeline import (
    PIPELINE_STAGES,
    build_export,
    build_text_export,
    camera_detection_failed,
    collect_ocr_duplicate_notes,
    mode_settings,
    ocr_and_collapse_duplicates,
)
from app.processing.searchable_exporter import export_searchable_pdf
from app.processing.page_fallback import FALLBACK_NOTE, ensure_pages_from_frames
from app.processing.preview import attach_previews
from app.processing.scoring import compute_frame_quality
from app.processing.sampler import load_video_metadata, sample_frames
from app.processing.sequence import collapse_sequence_candidates
from app.processing.segmenter import detect_stable_segments
from app.processing.selector import select_best_frames
from app.processing.types import FrameQuality, SampledFrame, SelectedPage
from app.schemas.job import (
    AddManualPageRequest,
    BlurRegionPayload,
    BulkUpdatePagesRequest,
    CropBoxPayload,
    DrawStrokePayload,
    EditPointPayload,
    ExportResponse,
    JobResponse,
    OcrBlockPayload,
    PageResponse,
    PageEditsPayload,
    ProgressResponse,
    ReorderPagesRequest,
    StageResponse,
    TextAnnotationPayload,
    UpdatePageRequest,
    UpdatePageEditsPayload,
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
        ocr_language: str = "eng",
        sensitivity: str = "balanced",
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
            ocr_language=sanitize_language(ocr_language),
            sensitivity=self._sanitize_sensitivity(sensitivity),
        )

        with self._lock:
            self._jobs[job_id] = job
            self._save_jobs()

        self._executor.submit(self._run_pipeline_job, job_id)
        return self._to_response(job)

    def create_job_from_url(
        self,
        url: str,
        processing_mode: ProcessingMode = "screen",
        ocr_language: str = "eng",
        sensitivity: str = "balanced",
    ) -> JobResponse | None:
        url = url.strip()
        if not is_valid_video_url(url):
            return None

        job_id = uuid4().hex[:12]
        created_at = datetime.now(timezone.utc)
        stages = [
            Stage(key="download_video", label="Download the video from the URL", status="pending"),
            *(Stage(key=key, label=label, status="pending") for key, label in PIPELINE_STAGES),
        ]
        job = Job(
            id=job_id,
            filename=url,
            processing_mode=processing_mode,
            status="queued",
            created_at=created_at,
            updated_at=created_at,
            progress=Progress(percent=1, message="Queued. The video will be downloaded first."),
            notes=[f"Job created from URL: {url}"],
            stages=stages,
            source_url=url,
            ocr_language=sanitize_language(ocr_language),
            sensitivity=self._sanitize_sensitivity(sensitivity),
        )

        with self._lock:
            self._jobs[job_id] = job
            self._save_jobs()

        self._executor.submit(self._run_url_job, job_id)
        return self._to_response(job)

    def _run_url_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not job.source_url:
                return
            source_url = job.source_url

        self._start_stage(job_id, "download_video", "Downloading the video.", 3)
        try:
            file_path, title = download_video(
                source_url,
                output_dir=str(self._uploads_root),
                job_id=job_id,
            )
        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.status = "failed"
                job.progress = Progress(percent=100, message="Video download failed.")
                job.notes.append(f"Download error: {exc}")
                for stage in job.stages:
                    if stage.status == "processing":
                        stage.status = "failed"
                job.updated_at = datetime.now(timezone.utc)
                self._save_jobs()
            return

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.upload_path = file_path
            job.filename = f"{title}{Path(file_path).suffix}"
        self._complete_stage(job_id, "download_video", 6, f"Downloaded “{title}”.")
        self._run_pipeline_job(job_id)

    def reprocess_job(self, job_id: str, sensitivity: str | None = None) -> JobResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not job.upload_path:
                return None
            if job.status in {"queued", "processing"}:
                return self._to_response(job)

            if sensitivity is not None:
                job.sensitivity = self._sanitize_sensitivity(sensitivity)
            job.status = "queued"
            job.pages = []
            job.notes = [f"Re-processing with sensitivity: {job.sensitivity}."]
            job.stages = [
                Stage(key=key, label=label, status="pending") for key, label in PIPELINE_STAGES
            ]
            job.current_stage_key = None
            job.completed_at = None
            job.progress = Progress(percent=2, message="Queued for re-processing.")
            self._invalidate_export(job)
            job.updated_at = datetime.now(timezone.utc)
            self._save_jobs()

        self._executor.submit(self._run_pipeline_job, job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            return None if job is None else self._to_response(job)

    @staticmethod
    def _sanitize_sensitivity(sensitivity: str | None) -> str:
        return sensitivity if sensitivity in {"fewer", "balanced", "more"} else "balanced"

    def update_page(self, job_id: str, page_id: str, payload: UpdatePageRequest) -> JobResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            page = next((page for page in job.pages if page.id == page_id), None)
            if page is None:
                return None

            needs_rerender = payload.rotation is not None or payload.edits is not None
            if payload.rotation is not None:
                page.edits.rotation = payload.rotation % 360
                page.rotation = page.edits.rotation
            if payload.edits is not None:
                page.edits = self._to_page_edits(payload.edits)
                page.rotation = page.edits.rotation
            if payload.deleted is not None:
                page.deleted = payload.deleted
                page.status = "deleted" if payload.deleted else "active"

            if needs_rerender and page.source_image_url and page.image_url and page.thumbnail_url:
                self._render_page_artifacts(page)
                # Rendering changed the pixels; invalidate OCR rather than
                # blocking this request on a synchronous Tesseract run. The
                # next text export re-OCRs any page that is not "ready".
                self._invalidate_page_ocr(page)

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
                    page.edits.rotation = payload.rotation % 360
                    page.rotation = page.edits.rotation
                    if page.source_image_url and page.image_url and page.thumbnail_url:
                        self._render_page_artifacts(page)
                        self._invalidate_page_ocr(page)
                if payload.deleted is not None:
                    page.deleted = payload.deleted
                    page.status = "deleted" if payload.deleted else "active"

            self._invalidate_export(job)
            job.updated_at = datetime.now(timezone.utc)
            self._save_jobs()
            return self._to_response(job)

    def add_manual_page(self, job_id: str, payload: AddManualPageRequest) -> JobResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not job.upload_path:
                return None
            upload_path = job.upload_path
            processing_mode = job.processing_mode
            ocr_language = job.ocr_language

        frame_index, timestamp, frame = self._extract_video_frame(upload_path, payload.timestampSeconds)
        if frame is None:
            return None

        if processing_mode == "camera":
            detection = detect_document_region(frame)
            processed_frame = detection.corrected_image
        else:
            detection = None
            processed_frame = frame

        quality = compute_frame_quality(
            processed_frame,
            mode=processing_mode,
            detection=detection,
            transition_penalty=0.0,
        )
        sampled_frame = SampledFrame(
            timestamp=timestamp,
            frame_index=frame_index,
            image=processed_frame,
            quality=quality,
            detection=detection,
            change_ratio=0.0,
        )
        manual_page = SelectedPage(
            page_id=f"manual-{uuid4().hex[:8]}",
            page_number=0,
            label="Manual page",
            source_segment_id=f"manual-{frame_index}",
            segment_start=timestamp,
            segment_end=timestamp,
            selected_frame=sampled_frame,
            image_path="",
            thumbnail_path="",
            notes=[
                f"Added manually from source video at {timestamp:.2f}s.",
                "Manual recovery page created from the current video frame.",
            ],
        )
        context = build_pipeline_context(job_id=job_id, upload_path=upload_path, processing_mode=processing_mode)
        attach_previews([manual_page], context=context)
        ocr_result = extract_page_text(
            manual_page.image_path,
            page_id=manual_page.page_id,
            page_number=0,
            lang=ocr_language,
        )

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            next_index = len(job.pages)
            ocr_result.page_number = next_index + 1
            job.pages.append(
                Page(
                    id=manual_page.page_id,
                    job_id=job.id,
                    order_index=next_index,
                    page_number=next_index + 1,
                    preview_label=f"Manual page {next_index + 1}",
                    thumbnail_url=manual_page.preview_url,
                    image_url=manual_page.image_url,
                    sharpness_score=manual_page.selected_frame.quality.score,
                    segment_start=manual_page.segment_start,
                    segment_end=manual_page.segment_end,
                    source_frame_index=manual_page.selected_frame.frame_index,
                    source_timestamp=manual_page.selected_frame.timestamp,
                    manual=True,
                    source_image_url=self._build_source_image_url(job.id, manual_page.page_id),
                    **self._ocr_fields_from_result(ocr_result),
                )
            )
            job.notes.append(f"Manual page added at {timestamp:.2f}s from the source video.")
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

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
            if job is None:
                return False
            upload_path = job.upload_path
            self._save_jobs()

        # Best-effort artifact cleanup outside the lock; state is already gone.
        job_dir = self._jobs_root / job_id
        if job_dir.is_dir():
            shutil.rmtree(job_dir, ignore_errors=True)
        text_work_dir = self._exports_root / f"{job_id}-text"
        if text_work_dir.is_dir():
            shutil.rmtree(text_work_dir, ignore_errors=True)
        for export_name in (f"{job_id}.pdf", f"{job_id}-text.pdf", f"{job_id}-searchable.pdf"):
            export_path = self._exports_root / export_name
            if export_path.is_file():
                export_path.unlink(missing_ok=True)
        if upload_path:
            upload_file = Path(upload_path)
            if upload_file.is_file():
                try:
                    upload_file.unlink()
                except OSError:
                    pass
        return True

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

    def export_text_job(self, job_id: str) -> ExportResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            if job.text_export.status == "processing":
                return self._to_export_response(job.text_export)

            now = datetime.now(timezone.utc)
            job.text_export = ExportArtifact(
                status="processing",
                progress_percent=5,
                requested_at=now,
            )
            job.updated_at = now
            self._save_jobs()

        self._executor.submit(self._run_text_export_job, job_id)
        return self._to_export_response(job.text_export)

    def export_searchable_job(self, job_id: str) -> ExportResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            if job.searchable_export.status == "processing":
                return self._to_export_response(job.searchable_export)

            now = datetime.now(timezone.utc)
            job.searchable_export = ExportArtifact(
                status="processing",
                progress_percent=5,
                requested_at=now,
            )
            job.updated_at = now
            self._save_jobs()

        self._executor.submit(self._run_searchable_export_job, job_id)
        return self._to_export_response(job.searchable_export)

    def _run_searchable_export_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            active_pages = [
                page for page in sorted(job.pages, key=lambda item: item.order_index) if not page.deleted
            ]
            if not active_pages:
                job.searchable_export.status = "failed"
                job.searchable_export.error = "No active pages available for export."
                job.updated_at = datetime.now(timezone.utc)
                self._save_jobs()
                return
            selected_pages = [self._to_selected_page(page) for page in active_pages]
            title = Path(job.filename).stem or f"Vid2PDF export {job_id}"
            ocr_language = job.ocr_language
            job.searchable_export.progress_percent = 25
            self._save_jobs()

        try:
            artifact = export_searchable_pdf(
                job_id=job_id,
                pages=selected_pages,
                output_dir=str(self._exports_root),
                title=title,
                lang=ocr_language,
            )
        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.searchable_export.status = "failed"
                job.searchable_export.progress_percent = 100
                job.searchable_export.error = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                self._save_jobs()
            return

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.searchable_export.status = "ready"
            job.searchable_export.progress_percent = 100
            job.searchable_export.filename = artifact.filename
            job.searchable_export.download_url = (
                f"{settings.public_artifact_base_url}/exports/{artifact.filename}"
            )
            job.searchable_export.completed_at = datetime.now(timezone.utc)
            job.searchable_export.error = None
            job.updated_at = job.searchable_export.completed_at
            self._save_jobs()

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
                sensitivity = job.sensitivity
                ocr_language = job.ocr_language
            if not upload_path:
                raise ValueError("Uploaded video path is missing.")

            context = build_pipeline_context(
                job_id=job_id,
                upload_path=upload_path,
                processing_mode=processing_mode,
            )
            settings_for_mode = mode_settings(processing_mode, sensitivity)
            pipeline_notes: list[str] = []

            self._start_stage(job_id, "sample_frames", "Sampling frames from the uploaded video.", 8)
            metadata = load_video_metadata(upload_path)
            sampled_frames = sample_frames(
                context=context,
                metadata=metadata,
                sample_fps=float(settings_for_mode["sample_fps"]),
            )

            if processing_mode == "camera" and camera_detection_failed(sampled_frames):
                pipeline_notes.append(
                    "Camera mode found no page contours; automatically switched to screen mode."
                )
                processing_mode = "screen"
                context = build_pipeline_context(
                    job_id=job_id,
                    upload_path=upload_path,
                    processing_mode="screen",
                )
                settings_for_mode = mode_settings("screen", sensitivity)
                sampled_frames = sample_frames(
                    context=context,
                    metadata=metadata,
                    sample_fps=float(settings_for_mode["sample_fps"]),
                )
                with self._lock:
                    job = self._jobs[job_id]
                    job.processing_mode = "screen"

            self._complete_stage(
                job_id,
                "sample_frames",
                24,
                f"Sampled {len(sampled_frames)} frames.",
            )

            self._start_stage(job_id, "detect_segments", "Detecting stable page-view segments.", 28)
            segments = detect_stable_segments(
                frames=sampled_frames,
                min_seconds=float(settings_for_mode["min_seconds"]),
                max_change_ratio=float(settings_for_mode["max_change_ratio"]),
                hash_distance_threshold=int(settings_for_mode["hash_distance_threshold"]),
                mean_diff_threshold=float(settings_for_mode["mean_diff_threshold"]),
                adaptive_std_scale=float(settings_for_mode["adaptive_std_scale"]),
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
                max_hamming_distance=int(settings_for_mode["dedupe_threshold"]),
            )
            unique_pages, used_fallback = ensure_pages_from_frames(
                unique_pages=unique_pages,
                sequence_pages=sequence_pages,
                selected_pages=selected_pages,
                sampled_frames=sampled_frames,
                processing_mode=processing_mode,
            )
            if used_fallback:
                pipeline_notes.append(FALLBACK_NOTE)
            self._complete_stage(
                job_id,
                "remove_duplicates",
                82,
                f"Kept {len(unique_pages)} pages after deduplication.",
            )

            self._start_stage(job_id, "prepare_previews", "Writing page previews and final page images.", 86)
            preview_pages = attach_previews(unique_pages, context=context)
            self._complete_stage(job_id, "prepare_previews", 90, "Preview artifacts written.")
            write_pipeline_debug_report(
                context=context,
                sampled_frames=sampled_frames,
                segments=segments,
                selected_pages=selected_pages,
                sequence_pages=sequence_pages,
                deduped_pages=preview_pages,
            )

            self._start_stage(job_id, "extract_text", "Extracting text from unique page frames.", 92)
            preview_pages, ocr_results, ocr_notes = ocr_and_collapse_duplicates(
                preview_pages, lang=ocr_language
            )
            ready_count = sum(1 for item in ocr_results if item.status == "ready")
            empty_count = sum(1 for item in ocr_results if item.status == "empty")
            failed_count = sum(1 for item in ocr_results if item.status == "failed")
            self._complete_stage(
                job_id,
                "extract_text",
                98,
                f"OCR complete: {ready_count} ready, {empty_count} empty, {failed_count} failed.",
            )
            ocr_by_page_id = {item.page_id: item for item in ocr_results}

            with self._lock:
                job = self._jobs[job_id]
                job.notes = [
                    f"Pipeline completed in {processing_mode} mode with background execution.",
                    "Pages can now be reviewed, reordered, rotated, deleted, and exported through backend-backed state.",
                    *pipeline_notes,
                    f"Processed video at {metadata.fps:.2f} fps, {metadata.width}x{metadata.height}, duration {metadata.duration_seconds:.1f}s.",
                    f"Sampled {len(sampled_frames)} frames and detected {len(segments)} stable page segments.",
                    f"Selected {len(selected_pages)} representative frames, collapsed to {len(sequence_pages)} sequence-stable candidates, removed {max(len(sequence_pages) - len(preview_pages), 0)} duplicates, and kept {len(preview_pages)} pages after deduplication.",
                    f"Extracted text from {len(ocr_results)} unique pages ({ready_count} with text).",
                ]
                job.notes.extend(ocr_notes)
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
                        source_image_url=self._build_source_image_url(job.id, page.page_id),
                        **self._ocr_fields_from_result(ocr_by_page_id.get(page.page_id)),
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
            title = Path(job.filename).stem or f"Vid2PDF export {job_id}"
            job.export.progress_percent = 35
            self._save_jobs()

        try:
            artifact = build_export(
                job_id=job_id,
                pages=selected_pages,
                output_dir=str(self._exports_root),
                title=title,
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

    def _run_text_export_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            active_pages = [
                page for page in sorted(job.pages, key=lambda item: item.order_index) if not page.deleted
            ]
            if not active_pages:
                job.text_export.status = "failed"
                job.text_export.error = "No active pages available for text export."
                job.updated_at = datetime.now(timezone.utc)
                self._save_jobs()
                return
            filename = job.filename
            ocr_language = job.ocr_language
            job.text_export.progress_percent = 20
            self._save_jobs()

        try:
            page_texts = self._collect_page_texts(active_pages, lang=ocr_language)

            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                for page, page_text in zip(active_pages, page_texts, strict=False):
                    stored = next((item for item in job.pages if item.id == page.id), None)
                    if stored is not None:
                        self._assign_ocr_result(stored, page_text)
                duplicate_notes = collect_ocr_duplicate_notes(page_texts)
                for note in duplicate_notes:
                    if note not in job.notes:
                        job.notes.append(note)
                job.text_export.progress_percent = 55
                self._save_jobs()

            artifact = build_text_export(
                job_id=job_id,
                pages=page_texts,
                output_dir=str(self._exports_root),
                title=Path(filename).stem or "Vid2PDF Export",
                source_filename=filename,
            )
        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.text_export.status = "failed"
                job.text_export.progress_percent = 100
                job.text_export.error = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                self._save_jobs()
            return

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.text_export.status = "ready"
            job.text_export.progress_percent = 100
            job.text_export.filename = artifact.filename
            job.text_export.download_url = (
                f"{settings.public_artifact_base_url}/exports/{artifact.filename}"
            )
            job.text_export.tex_url = self._artifact_url_for_path(artifact.tex_path)
            job.text_export.completed_at = datetime.now(timezone.utc)
            job.text_export.error = None
            job.updated_at = job.text_export.completed_at
            self._save_jobs()

    def _collect_page_texts(self, active_pages: list[Page], lang: str | None = None) -> list[PageText]:
        """Reuse successful OCR; re-run the rest in parallel across pages."""
        results: list[PageText | None] = [None] * len(active_pages)
        pending: list[tuple[int, str, str, int]] = []

        for index, page in enumerate(active_pages):
            page_number = index + 1
            # Only reuse successful OCR. Re-run empty/failed so improved settings apply.
            if page.ocr_status == "ready" and page.ocr_text:
                results[index] = PageText(
                    page_id=page.id,
                    page_number=page_number,
                    blocks=[
                        TextBlock(
                            text=block.text,
                            confidence=block.confidence,
                            top=block.top,
                            left=block.left,
                        )
                        for block in page.ocr_blocks
                    ],
                    raw_text=page.ocr_text,
                    status=page.ocr_status,
                    error=page.ocr_error,
                )
            elif not page.image_url:
                results[index] = PageText(
                    page_id=page.id,
                    page_number=page_number,
                    status="failed",
                    error="Page image is missing for OCR.",
                )
            else:
                image_path = str(self._resolve_storage_path(page.image_url))
                pending.append((index, image_path, page.id, page_number))

        if pending:
            ocr_results = extract_pages_text_parallel(
                [(image_path, page_id, page_number) for _, image_path, page_id, page_number in pending],
                lang=lang,
            )
            for (index, _, _, _), result in zip(pending, ocr_results, strict=True):
                results[index] = result

        return [item for item in results if item is not None]

    def _invalidate_page_ocr(self, page: Page) -> None:
        page.ocr_status = "pending"
        page.ocr_text = None
        page.ocr_blocks = []
        page.ocr_error = None

    def _assign_ocr_result(self, page: Page, result: PageText) -> None:
        page.ocr_text = result.raw_text if result.status in {"ready", "empty"} else None
        page.ocr_blocks = [
            OcrBlock(
                text=block.text,
                confidence=block.confidence,
                top=block.top,
                left=block.left,
            )
            for block in result.blocks
        ]
        if result.status in {"ready", "empty", "failed"}:
            page.ocr_status = result.status  # type: ignore[assignment]
        else:
            page.ocr_status = "failed"
        page.ocr_error = result.error

    def _ocr_fields_from_result(self, result: PageText | None) -> dict:
        if result is None:
            return {
                "ocr_text": None,
                "ocr_blocks": [],
                "ocr_status": "pending",
                "ocr_error": None,
            }
        return {
            "ocr_text": result.raw_text if result.status in {"ready", "empty"} else None,
            "ocr_blocks": [
                OcrBlock(
                    text=block.text,
                    confidence=block.confidence,
                    top=block.top,
                    left=block.left,
                )
                for block in result.blocks
            ],
            "ocr_status": result.status if result.status in {"ready", "empty", "failed"} else "failed",
            "ocr_error": result.error,
        }

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
                if job.text_export.status == "processing":
                    job.text_export.status = "failed"
                    job.text_export.error = "Text export interrupted by server restart."
                    changed = True
                if job.searchable_export.status == "processing":
                    job.searchable_export.status = "failed"
                    job.searchable_export.error = "Searchable export interrupted by server restart."
                    changed = True
            if changed:
                self._save_jobs()

    def _extract_video_frame(
        self,
        upload_path: str,
        requested_timestamp: float,
    ) -> tuple[int, float, object | None]:
        capture = cv2.VideoCapture(upload_path)
        if not capture.isOpened():
            return -1, requested_timestamp, None

        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        clamped_timestamp = max(requested_timestamp, 0.0)
        if fps > 0 and frame_count > 0:
            max_timestamp = max((frame_count - 1) / fps, 0.0)
            clamped_timestamp = min(clamped_timestamp, max_timestamp)

        capture.set(cv2.CAP_PROP_POS_MSEC, clamped_timestamp * 1000.0)
        success, frame = capture.read()
        if not success and fps > 0:
            frame_index = min(max(int(round(clamped_timestamp * fps)), 0), max(frame_count - 1, 0))
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            success, frame = capture.read()
        else:
            frame_index = int(capture.get(cv2.CAP_PROP_POS_FRAMES) or 0)

        capture.release()
        if not success:
            return -1, clamped_timestamp, None
        timestamp = (frame_index / fps) if fps > 0 else clamped_timestamp
        return frame_index, timestamp, frame

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
            sourceVideoUrl=self._source_video_url(job),
            sourceUrl=job.source_url,
            ocrLanguage=job.ocr_language,
            sensitivity=job.sensitivity,
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
                    sourceImageUrl=page.source_image_url,
                    sharpnessScore=page.sharpness_score,
                    segmentStart=page.segment_start,
                    segmentEnd=page.segment_end,
                    sourceFrameIndex=page.source_frame_index,
                    sourceTimestamp=page.source_timestamp,
                    manual=page.manual,
                    rotation=page.rotation,
                    status=page.status,
                    deleted=page.deleted,
                    edits=self._to_page_edits_response(page.edits),
                    ocrText=page.ocr_text,
                    ocrBlocks=[
                        OcrBlockPayload(
                            text=block.text,
                            confidence=block.confidence,
                            top=block.top,
                            left=block.left,
                        )
                        for block in page.ocr_blocks
                    ],
                    ocrStatus=page.ocr_status,
                    ocrError=page.ocr_error,
                )
                for page in pages
            ],
            export=self._to_export_response(job.export),
            textExport=self._to_export_response(job.text_export),
            searchableExport=self._to_export_response(job.searchable_export),
        )

    def _to_export_response(self, export: ExportArtifact) -> ExportResponse:
        return ExportResponse(
            status=export.status,
            progressPercent=export.progress_percent,
            filename=export.filename,
            downloadUrl=export.download_url,
            texUrl=export.tex_url,
            requestedAt=export.requested_at,
            completedAt=export.completed_at,
            error=export.error,
        )

    def _artifact_url_for_path(self, file_path: str | None) -> str | None:
        if not file_path:
            return None
        try:
            relative = Path(file_path).resolve().relative_to(self._storage_root.resolve())
        except ValueError:
            return None
        return f"{settings.public_artifact_base_url}/{relative.as_posix()}"

    def _to_page_edits(
        self,
        payload: UpdatePageEditsPayload,
    ) -> PageEdits:
        return PageEdits(
            rotation=payload.rotation % 360,
            filter=payload.filter,
            crop=None
            if payload.crop is None
            else CropBox(
                x=payload.crop.x,
                y=payload.crop.y,
                width=payload.crop.width,
                height=payload.crop.height,
            ),
            strokes=[
                DrawStroke(
                    color=stroke.color,
                    width=stroke.width,
                    points=[EditPoint(x=point.x, y=point.y) for point in stroke.points],
                )
                for stroke in payload.strokes
            ],
            texts=[
                TextAnnotation(
                    text=text.text,
                    x=text.x,
                    y=text.y,
                    color=text.color,
                    font_size=text.fontSize,
                )
                for text in payload.texts
            ],
            blur_regions=[
                BlurRegion(
                    x=region.x,
                    y=region.y,
                    width=region.width,
                    height=region.height,
                    intensity=region.intensity,
                )
                for region in payload.blurRegions
            ],
        )

    def _to_page_edits_response(
        self,
        edits: PageEdits,
    ) -> PageEditsPayload:
        crop = None
        if edits.crop is not None:
            crop = CropBoxPayload(
                x=edits.crop.x,
                y=edits.crop.y,
                width=edits.crop.width,
                height=edits.crop.height,
            )

        return PageEditsPayload(
            rotation=edits.rotation,
            filter=edits.filter,
            crop=crop,
            strokes=[
                DrawStrokePayload(
                    color=stroke.color,
                    width=stroke.width,
                    points=[
                        EditPointPayload(x=point.x, y=point.y)
                        for point in stroke.points
                    ],
                )
                for stroke in edits.strokes
            ],
            texts=[
                TextAnnotationPayload(
                    text=text.text,
                    x=text.x,
                    y=text.y,
                    color=text.color,
                    fontSize=text.font_size,
                )
                for text in edits.texts
            ],
            blurRegions=[
                BlurRegionPayload(
                    x=region.x,
                    y=region.y,
                    width=region.width,
                    height=region.height,
                    intensity=region.intensity,
                )
                for region in edits.blur_regions
            ],
        )

    def _serialize_page_edits(self, edits: PageEdits) -> dict[str, object]:
        return {
            "rotation": edits.rotation,
            "filter": edits.filter,
            "crop": None
            if edits.crop is None
            else {
                "x": edits.crop.x,
                "y": edits.crop.y,
                "width": edits.crop.width,
                "height": edits.crop.height,
            },
            "strokes": [
                {
                    "color": stroke.color,
                    "width": stroke.width,
                    "points": [{"x": point.x, "y": point.y} for point in stroke.points],
                }
                for stroke in edits.strokes
            ],
            "texts": [
                {
                    "text": text.text,
                    "x": text.x,
                    "y": text.y,
                    "color": text.color,
                    "font_size": text.font_size,
                }
                for text in edits.texts
            ],
            "blur_regions": [
                {
                    "x": region.x,
                    "y": region.y,
                    "width": region.width,
                    "height": region.height,
                    "intensity": region.intensity,
                }
                for region in edits.blur_regions
            ],
        }

    def _deserialize_page_edits(self, payload: object) -> PageEdits:
        if not isinstance(payload, dict):
            return PageEdits()

        crop_payload = payload.get("crop")
        crop = None
        if isinstance(crop_payload, dict):
            crop = CropBox(
                x=int(crop_payload.get("x", 0)),
                y=int(crop_payload.get("y", 0)),
                width=int(crop_payload.get("width", 0)),
                height=int(crop_payload.get("height", 0)),
            )

        strokes = []
        for stroke_payload in payload.get("strokes", []):
            if not isinstance(stroke_payload, dict):
                continue
            strokes.append(
                DrawStroke(
                    color=str(stroke_payload.get("color", "#111111")),
                    width=int(stroke_payload.get("width", 2)),
                    points=[
                        EditPoint(x=float(point.get("x", 0.0)), y=float(point.get("y", 0.0)))
                        for point in stroke_payload.get("points", [])
                        if isinstance(point, dict)
                    ],
                )
            )

        texts = []
        for text_payload in payload.get("texts", []):
            if not isinstance(text_payload, dict):
                continue
            texts.append(
                TextAnnotation(
                    text=str(text_payload.get("text", "")),
                    x=float(text_payload.get("x", 0.0)),
                    y=float(text_payload.get("y", 0.0)),
                    color=str(text_payload.get("color", "#111111")),
                    font_size=int(text_payload.get("font_size", 24)),
                )
            )

        blur_regions = []
        for region_payload in payload.get("blur_regions", []):
            if not isinstance(region_payload, dict):
                continue
            blur_regions.append(
                BlurRegion(
                    x=int(region_payload.get("x", 0)),
                    y=int(region_payload.get("y", 0)),
                    width=int(region_payload.get("width", 0)),
                    height=int(region_payload.get("height", 0)),
                    intensity=int(region_payload.get("intensity", 18)),
                )
            )

        stored_filter = payload.get("filter", "none")
        if stored_filter not in {"none", "enhance", "grayscale", "bw"}:
            stored_filter = "none"

        return PageEdits(
            rotation=int(payload.get("rotation", 0)) % 360,
            filter=stored_filter,  # type: ignore[arg-type]
            crop=crop,
            strokes=strokes,
            texts=texts,
            blur_regions=blur_regions,
        )

    def _build_source_image_url(self, job_id: str, page_id: str) -> str:
        return f"{settings.public_artifact_base_url}/jobs/{job_id}/source-pages/{page_id}-source.png"

    def _render_page_artifacts(self, page: Page) -> None:
        if not page.source_image_url or not page.image_url or not page.thumbnail_url:
            raise ValueError("Page artifacts are incomplete for editing.")
        write_rendered_page(
            source_image_path=str(self._resolve_storage_path(page.source_image_url)),
            output_image_path=str(self._resolve_storage_path(page.image_url)),
            thumbnail_path=str(self._resolve_storage_path(page.thumbnail_url)),
            edits=page.edits,
        )

    def _source_video_url(self, job: Job) -> str | None:
        if not job.upload_path:
            return None
        upload_path = Path(job.upload_path)
        try:
            relative_path = upload_path.relative_to(self._storage_root)
        except ValueError:
            return None
        return f"{settings.public_artifact_base_url}/{relative_path.as_posix()}"

    def _invalidate_export(self, job: Job) -> None:
        job.export = ExportArtifact()
        job.text_export = ExportArtifact()
        job.searchable_export = ExportArtifact()

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
                    "manual": page.manual,
                    "rotation": page.rotation,
                    "status": page.status,
                    "deleted": page.deleted,
                    "source_image_url": page.source_image_url,
                    "edits": self._serialize_page_edits(page.edits),
                    "ocr_text": page.ocr_text,
                    "ocr_blocks": [
                        {
                            "text": block.text,
                            "confidence": block.confidence,
                            "top": block.top,
                            "left": block.left,
                        }
                        for block in page.ocr_blocks
                    ],
                    "ocr_status": page.ocr_status,
                    "ocr_error": page.ocr_error,
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
            "text_export": {
                "status": job.text_export.status,
                "progress_percent": job.text_export.progress_percent,
                "filename": job.text_export.filename,
                "download_url": job.text_export.download_url,
                "tex_url": job.text_export.tex_url,
                "requested_at": self._serialize_datetime(job.text_export.requested_at),
                "completed_at": self._serialize_datetime(job.text_export.completed_at),
                "error": job.text_export.error,
            },
            "searchable_export": {
                "status": job.searchable_export.status,
                "progress_percent": job.searchable_export.progress_percent,
                "filename": job.searchable_export.filename,
                "download_url": job.searchable_export.download_url,
                "requested_at": self._serialize_datetime(job.searchable_export.requested_at),
                "completed_at": self._serialize_datetime(job.searchable_export.completed_at),
                "error": job.searchable_export.error,
            },
            "upload_path": job.upload_path,
            "source_url": job.source_url,
            "ocr_language": job.ocr_language,
            "sensitivity": job.sensitivity,
        }

    def _deserialize_job(self, payload: dict[str, object]) -> Job:
        progress_payload = payload.get("progress", {})
        export_payload = payload.get("export", {})
        text_export_payload = payload.get("text_export", {})
        searchable_payload = payload.get("searchable_export", {})
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
                    manual=bool(page.get("manual", False)),
                    rotation=int(page.get("rotation", 0)),
                    status=page.get("status", "active"),  # type: ignore[arg-type]
                    deleted=bool(page.get("deleted", False)),
                    source_image_url=page.get("source_image_url", page.get("image_url")),  # type: ignore[arg-type]
                    edits=self._deserialize_page_edits(page.get("edits")),
                    ocr_text=page.get("ocr_text"),  # type: ignore[arg-type]
                    ocr_blocks=[
                        OcrBlock(
                            text=str(block.get("text", "")),
                            confidence=float(block.get("confidence", 0)),
                            top=int(block.get("top", 0)),
                            left=int(block.get("left", 0)),
                        )
                        for block in page.get("ocr_blocks", [])  # type: ignore[union-attr]
                    ],
                    ocr_status=page.get("ocr_status", "pending"),  # type: ignore[arg-type]
                    ocr_error=page.get("ocr_error"),  # type: ignore[arg-type]
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
            text_export=ExportArtifact(
                status=text_export_payload.get("status", "idle") if isinstance(text_export_payload, dict) else "idle",  # type: ignore[arg-type]
                progress_percent=int(text_export_payload.get("progress_percent", 0)) if isinstance(text_export_payload, dict) else 0,  # type: ignore[union-attr]
                filename=text_export_payload.get("filename") if isinstance(text_export_payload, dict) else None,  # type: ignore[arg-type]
                download_url=text_export_payload.get("download_url") if isinstance(text_export_payload, dict) else None,  # type: ignore[arg-type]
                tex_url=text_export_payload.get("tex_url") if isinstance(text_export_payload, dict) else None,  # type: ignore[arg-type]
                requested_at=self._deserialize_datetime(text_export_payload.get("requested_at")) if isinstance(text_export_payload, dict) else None,  # type: ignore[union-attr]
                completed_at=self._deserialize_datetime(text_export_payload.get("completed_at")) if isinstance(text_export_payload, dict) else None,  # type: ignore[union-attr]
                error=text_export_payload.get("error") if isinstance(text_export_payload, dict) else None,  # type: ignore[arg-type]
            ),
            searchable_export=ExportArtifact(
                status=searchable_payload.get("status", "idle") if isinstance(searchable_payload, dict) else "idle",  # type: ignore[arg-type]
                progress_percent=int(searchable_payload.get("progress_percent", 0)) if isinstance(searchable_payload, dict) else 0,  # type: ignore[union-attr]
                filename=searchable_payload.get("filename") if isinstance(searchable_payload, dict) else None,  # type: ignore[arg-type]
                download_url=searchable_payload.get("download_url") if isinstance(searchable_payload, dict) else None,  # type: ignore[arg-type]
                requested_at=self._deserialize_datetime(searchable_payload.get("requested_at")) if isinstance(searchable_payload, dict) else None,  # type: ignore[union-attr]
                completed_at=self._deserialize_datetime(searchable_payload.get("completed_at")) if isinstance(searchable_payload, dict) else None,  # type: ignore[union-attr]
                error=searchable_payload.get("error") if isinstance(searchable_payload, dict) else None,  # type: ignore[arg-type]
            ),
            upload_path=payload.get("upload_path"),  # type: ignore[arg-type]
            source_url=payload.get("source_url"),  # type: ignore[arg-type]
            ocr_language=sanitize_language(str(payload.get("ocr_language", "eng"))),
            sensitivity=self._sanitize_sensitivity(str(payload.get("sensitivity", "balanced"))),  # type: ignore[arg-type]
        )

    def _serialize_datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    def _deserialize_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(str(value))


job_service = JobService()
