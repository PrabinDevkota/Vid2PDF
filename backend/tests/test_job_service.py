from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.settings import settings
from app.main import app
from app.models.job import ExportArtifact, Job, Page
from app.schemas.job import UpdatePageRequest
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


def test_upload_rejects_invalid_processing_mode() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/jobs/upload",
        files={"file": ("demo.mp4", b"fake-video", "video/mp4")},
        data={"processing_mode": "invalid"},
    )

    assert response.status_code == 422
