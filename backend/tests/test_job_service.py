from datetime import datetime, timezone

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.core.settings import settings
from app.main import app
from app.models.job import ExportArtifact, Job, Page, PageEdits, Stage
from app.schemas.job import (
    AddManualPageRequest,
    BlurRegionPayload,
    BulkUpdatePagesRequest,
    CropBoxPayload,
    DrawStrokePayload,
    EditPointPayload,
    TextAnnotationPayload,
    UpdatePageEditsPayload,
    UpdatePageRequest,
)
from app.services.job_service import JobService


def test_update_page_can_restore_deleted_page(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    now = datetime.now(timezone.utc)
    job = Job(
        id="job-restore",
        filename="demo.mp4",
        processing_mode="screen",
        status="ready",
        created_at=now,
        updated_at=now,
        pages=[
            Page(
                id="page-1",
                job_id="job-restore",
                order_index=0,
                page_number=1,
                preview_label="Page 1",
                thumbnail_url="/artifacts/jobs/job-restore/thumbnails/page-1-thumb.jpg",
                image_url="/artifacts/jobs/job-restore/pages/page-1.png",
                sharpness_score=0.9,
                segment_start=0.0,
                segment_end=1.0,
                source_frame_index=12,
                source_timestamp=0.5,
                status="deleted",
                deleted=True,
            )
        ],
        export=ExportArtifact(status="ready", filename="job-restore.pdf"),
    )
    service._jobs[job.id] = job

    response = service.update_page(job.id, "page-1", UpdatePageRequest(deleted=False))

    assert response is not None
    assert response.pages[0].deleted is False
    assert response.pages[0].status == "active"
    assert response.export.status == "idle"


def test_bulk_update_pages_marks_multiple_pages_deleted(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    now = datetime.now(timezone.utc)
    job = Job(
        id="job-bulk",
        filename="bulk.mp4",
        processing_mode="screen",
        status="ready",
        created_at=now,
        updated_at=now,
        pages=[
            Page(
                id="page-1",
                job_id="job-bulk",
                order_index=0,
                page_number=1,
                preview_label="Page 1",
                thumbnail_url="/artifacts/jobs/job-bulk/thumbnails/page-1-thumb.jpg",
                image_url="/artifacts/jobs/job-bulk/pages/page-1.png",
                sharpness_score=0.9,
                segment_start=0.0,
                segment_end=1.0,
                source_frame_index=10,
                source_timestamp=0.4,
            ),
            Page(
                id="page-2",
                job_id="job-bulk",
                order_index=1,
                page_number=2,
                preview_label="Page 2",
                thumbnail_url="/artifacts/jobs/job-bulk/thumbnails/page-2-thumb.jpg",
                image_url="/artifacts/jobs/job-bulk/pages/page-2.png",
                sharpness_score=0.8,
                segment_start=1.0,
                segment_end=2.0,
                source_frame_index=20,
                source_timestamp=1.4,
            ),
        ],
    )
    service._jobs[job.id] = job

    response = service.bulk_update_pages(
        job.id,
        BulkUpdatePagesRequest(pageIds=["page-1", "page-2"], deleted=True),
    )

    assert response is not None
    assert all(page.deleted for page in response.pages)
    assert all(page.status == "deleted" for page in response.pages)


def test_job_service_reloads_saved_jobs(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    now = datetime.now(timezone.utc)
    service._jobs["job-persist"] = Job(
        id="job-persist",
        filename="saved.mp4",
        processing_mode="screen",
        status="ready",
        created_at=now,
        updated_at=now,
        pages=[
            Page(
                id="page-1",
                job_id="job-persist",
                order_index=0,
                page_number=1,
                preview_label="Page 1",
                thumbnail_url="/artifacts/jobs/job-persist/thumbnails/page-1-thumb.jpg",
                image_url="/artifacts/jobs/job-persist/pages/page-1.png",
                sharpness_score=0.9,
                segment_start=0.0,
                segment_end=1.0,
                source_frame_index=4,
                source_timestamp=0.2,
            )
        ],
        export=ExportArtifact(status="ready", filename="job-persist.pdf"),
    )
    service._save_jobs()

    reloaded_service = JobService()
    reloaded = reloaded_service.get_job("job-persist")

    assert reloaded is not None
    assert reloaded.filename == "saved.mp4"
    assert reloaded.pages[0].id == "page-1"
    assert reloaded.export.filename == "job-persist.pdf"


def test_job_service_marks_interrupted_jobs_failed_after_reload(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    now = datetime.now(timezone.utc)
    service._jobs["job-interrupted"] = Job(
        id="job-interrupted",
        filename="stuck.mp4",
        processing_mode="screen",
        status="processing",
        created_at=now,
        updated_at=now,
        stages=[
            Stage(
                key="sample_frames",
                label="Sample frames",
                status="processing",
                progress_percent=50,
                started_at=now,
            )
        ],
        export=ExportArtifact(status="processing", progress_percent=35, requested_at=now),
    )
    service._save_jobs()

    reloaded_service = JobService()
    reloaded = reloaded_service.get_job("job-interrupted")

    assert reloaded is not None
    assert reloaded.status == "failed"
    assert reloaded.progress.message == "Processing interrupted by server restart."
    assert reloaded.export.status == "failed"


def test_add_manual_page_persists_artifacts_and_export_state(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    now = datetime.now(timezone.utc)
    video_path = tmp_path / "uploads" / "manual-test.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)

    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5.0,
        (160, 120),
    )
    for index in range(10):
        frame = np.full((120, 160, 3), 240, dtype=np.uint8)
        cv2.putText(
            frame,
            f"Page {index}",
            (20, 65),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (30, 30, 30),
            2,
            cv2.LINE_AA,
        )
        writer.write(frame)
    writer.release()

    job = Job(
        id="job-manual",
        filename="manual.mp4",
        processing_mode="screen",
        status="ready",
        created_at=now,
        updated_at=now,
        upload_path=str(video_path),
        pages=[
            Page(
                id="page-1",
                job_id="job-manual",
                order_index=0,
                page_number=1,
                preview_label="Page 1",
                thumbnail_url="/artifacts/jobs/job-manual/thumbnails/page-1-thumb.jpg",
                image_url="/artifacts/jobs/job-manual/pages/page-1.png",
                sharpness_score=0.9,
                segment_start=0.0,
                segment_end=1.0,
                source_frame_index=3,
                source_timestamp=0.6,
            )
        ],
        export=ExportArtifact(status="ready", filename="job-manual.pdf"),
    )
    service._jobs[job.id] = job

    response = service.add_manual_page(job.id, AddManualPageRequest(timestampSeconds=0.8))

    assert response is not None
    assert len(response.pages) == 2
    manual_page = response.pages[-1]
    assert manual_page.manual is True
    assert manual_page.deleted is False
    assert manual_page.thumbnailUrl is not None
    assert manual_page.imageUrl is not None
    assert response.export.status == "idle"
    assert "uploads/manual-test.mp4" in (response.sourceVideoUrl or "")
    assert (tmp_path / manual_page.thumbnailUrl.removeprefix("/artifacts/")).exists()
    assert (tmp_path / manual_page.imageUrl.removeprefix("/artifacts/")).exists()


def test_upload_rejects_invalid_processing_mode() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/jobs/upload",
        files={"file": ("demo.mp4", b"fake-video", "video/mp4")},
        data={"processing_mode": "invalid"},
    )

    assert response.status_code == 422


def test_update_page_persists_crop_blur_and_text_edits(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    now = datetime.now(timezone.utc)
    source_dir = tmp_path / "jobs" / "job-edit" / "source-pages"
    page_dir = tmp_path / "jobs" / "job-edit" / "pages"
    thumb_dir = tmp_path / "jobs" / "job-edit" / "thumbnails"
    source_dir.mkdir(parents=True, exist_ok=True)
    page_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    image = np.full((220, 180, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (160, 180), (230, 230, 230), thickness=-1)
    cv2.putText(image, "Secret", (42, 104), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (10, 10, 10), 2, cv2.LINE_AA)
    source_path = source_dir / "page-1-source.png"
    image_path = page_dir / "page-1.png"
    thumb_path = thumb_dir / "page-1-thumb.jpg"
    cv2.imwrite(str(source_path), image)
    cv2.imwrite(str(image_path), image)
    cv2.imwrite(str(thumb_path), image)

    job = Job(
        id="job-edit",
        filename="edit.mp4",
        processing_mode="screen",
        status="ready",
        created_at=now,
        updated_at=now,
        pages=[
            Page(
                id="page-1",
                job_id="job-edit",
                order_index=0,
                page_number=1,
                preview_label="Page 1",
                thumbnail_url="/artifacts/jobs/job-edit/thumbnails/page-1-thumb.jpg",
                image_url="/artifacts/jobs/job-edit/pages/page-1.png",
                source_image_url="/artifacts/jobs/job-edit/source-pages/page-1-source.png",
                sharpness_score=0.92,
                segment_start=0.0,
                segment_end=1.0,
                source_frame_index=4,
                source_timestamp=0.2,
            )
        ],
        export=ExportArtifact(status="ready", filename="job-edit.pdf"),
    )
    service._jobs[job.id] = job

    response = service.update_page(
        job.id,
        "page-1",
        UpdatePageRequest(
            edits=UpdatePageEditsPayload(
                rotation=90,
                crop=CropBoxPayload(x=10, y=12, width=120, height=140),
                strokes=[
                    DrawStrokePayload(
                        color="#ff0000",
                        width=6,
                        points=[
                            EditPointPayload(x=10, y=20),
                            EditPointPayload(x=80, y=26),
                        ],
                    )
                ],
                texts=[
                    TextAnnotationPayload(
                        text="Approved",
                        x=18,
                        y=44,
                        color="#0000ff",
                        fontSize=22,
                    )
                ],
                blurRegions=[
                    BlurRegionPayload(
                        x=30,
                        y=50,
                        width=50,
                        height=32,
                        intensity=21,
                    )
                ],
            )
        ),
    )

    assert response is not None
    assert response.export.status == "idle"
    assert response.pages[0].rotation == 90
    assert response.pages[0].edits.crop is not None
    assert response.pages[0].edits.crop.width == 120
    assert response.pages[0].edits.texts[0].text == "Approved"

    rendered = cv2.imread(str(image_path))
    thumbnail = cv2.imread(str(thumb_path))
    assert rendered is not None
    assert thumbnail is not None
    assert rendered.shape[1] == 120
    assert rendered.shape[0] == 140
    assert not np.array_equal(rendered, image)
    assert service._jobs[job.id].pages[0].edits != PageEdits()


def _document_scene_image() -> np.ndarray:
    """Bright paper on a dark desk with a hand-like blob outside the page."""
    image = np.full((420, 320, 3), (58, 82, 106), dtype=np.uint8)
    cv2.rectangle(image, (48, 40), (270, 380), (244, 243, 238), thickness=-1)
    cv2.rectangle(image, (66, 70), (250, 96), (25, 25, 25), thickness=-1)
    cv2.rectangle(image, (66, 130), (250, 150), (30, 30, 30), thickness=-1)
    cv2.ellipse(image, (300, 400), (48, 34), 0, 0, 360, (86, 118, 172), thickness=-1)
    return image


def _seed_croppable_job(service: JobService, tmp_path, job_id: str = "job-crop") -> np.ndarray:
    now = datetime.now(timezone.utc)
    source_dir = tmp_path / "jobs" / job_id / "source-pages"
    page_dir = tmp_path / "jobs" / job_id / "pages"
    thumb_dir = tmp_path / "jobs" / job_id / "thumbnails"
    source_dir.mkdir(parents=True, exist_ok=True)
    page_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    image = _document_scene_image()
    cv2.imwrite(str(source_dir / "page-1-source.png"), image)
    cv2.imwrite(str(page_dir / "page-1.png"), image)
    cv2.imwrite(str(thumb_dir / "page-1-thumb.jpg"), image)

    service._jobs[job_id] = Job(
        id=job_id,
        filename="crop.mp4",
        processing_mode="camera",
        status="ready",
        created_at=now,
        updated_at=now,
        pages=[
            Page(
                id="page-1",
                job_id=job_id,
                order_index=0,
                page_number=1,
                preview_label="Page 1",
                thumbnail_url=f"/artifacts/jobs/{job_id}/thumbnails/page-1-thumb.jpg",
                image_url=f"/artifacts/jobs/{job_id}/pages/page-1.png",
                source_image_url=f"/artifacts/jobs/{job_id}/source-pages/page-1-source.png",
                sharpness_score=0.9,
                segment_start=0.0,
                segment_end=1.0,
                source_frame_index=4,
                source_timestamp=0.2,
            )
        ],
        export=ExportArtifact(status="ready", filename=f"{job_id}.pdf"),
    )
    return image


def test_suggest_page_crop_returns_document_box(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    image = _seed_croppable_job(service, tmp_path)

    suggestion = service.suggest_page_crop("job-crop", "page-1", rotation=0)

    assert suggestion is not None
    assert suggestion.crop is not None
    assert suggestion.crop.width < image.shape[1]
    assert suggestion.crop.height < image.shape[0]
    # The suggested crop should cover the page rectangle drawn at (48,40)-(270,380).
    assert suggestion.crop.x <= 48
    assert suggestion.crop.y <= 40
    assert suggestion.crop.x + suggestion.crop.width >= 270

    assert service.suggest_page_crop("job-crop", "missing-page", rotation=0) is None
    assert service.suggest_page_crop("missing-job", "page-1", rotation=0) is None


def test_auto_crop_pages_crops_and_rerenders_active_pages(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = JobService()
    image = _seed_croppable_job(service, tmp_path)

    response = service.auto_crop_pages("job-crop")

    assert response is not None
    page = response.pages[0]
    assert page.edits.crop is not None
    assert page.edits.crop.width < image.shape[1]
    assert response.export.status == "idle"

    rendered = cv2.imread(str(tmp_path / "jobs" / "job-crop" / "pages" / "page-1.png"))
    assert rendered is not None
    assert rendered.shape[1] == page.edits.crop.width
    assert rendered.shape[0] == page.edits.crop.height
    # The cropped render keeps the bright page rather than the dark desk.
    assert float(np.mean(rendered)) > 150
