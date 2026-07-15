"""Tests for the improvement batch: deskew, export options, merged export,
editable OCR text, camera color output, atomic saves, storage cleanup."""
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
from pypdf import PdfReader

from app.core.settings import settings
from app.models.job import ExportArtifact, Job, Page, PageEdits
from app.processing.context import build_pipeline_context
from app.processing.document import estimate_skew_angle
from app.processing.editor import apply_page_edits, fine_rotate_image
from app.processing.exporter import export_merged_pdf, export_pdf
from app.schemas.job import MergedExportRequest, UpdatePageRequest
from app.services.job_service import JobService

from tests.test_export_quality import _make_page, _noisy_text_image


def _tilted_text_image(angle: float) -> np.ndarray:
    image = np.full((600, 440, 3), 250, dtype=np.uint8)
    for row in range(80, 520, 40):
        cv2.line(image, (40, row), (400, row), (30, 30, 30), 3)
    return fine_rotate_image(image, angle)


def test_estimate_skew_angle_round_trip() -> None:
    for induced in (-4.0, 3.0):
        tilted = _tilted_text_image(induced)
        estimate = estimate_skew_angle(tilted)
        assert estimate is not None
        corrected = fine_rotate_image(tilted, estimate)
        residual = estimate_skew_angle(corrected)
        # After correction the remaining tilt must be negligible.
        assert residual is None or abs(residual) < 0.6

    level = np.full((300, 300, 3), 250, dtype=np.uint8)
    for row in range(60, 260, 40):
        cv2.line(level, (30, row), (270, row), (30, 30, 30), 3)
    angle = estimate_skew_angle(level)
    assert angle is None or abs(angle) < 0.3


def test_apply_page_edits_fine_rotation(tmp_path) -> None:
    image = np.full((200, 200, 3), 255, dtype=np.uint8)
    cv2.line(image, (20, 100), (180, 100), (0, 0, 0), 5)
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), image)

    rotated = apply_page_edits(str(path), PageEdits(fine_rotation=8.0))
    assert rotated.shape == image.shape
    assert not np.array_equal(rotated, image)
    # The line's endpoints move vertically when tilted.
    column_dark = np.where(np.mean(rotated[:, 30], axis=-1) < 100)[0]
    assert column_dark.size > 0
    assert abs(int(column_dark.mean()) - 100) > 5


def test_export_pdf_with_fixed_page_size(tmp_path) -> None:
    image = _noisy_text_image()
    pages = [_make_page(tmp_path, "page-a4", image)]

    artifact = export_pdf(
        "job-a4", pages, str(tmp_path), title="A4 check", page_size="a4", margin="small"
    )
    reader = PdfReader(str(tmp_path / artifact.filename))
    box = reader.pages[0].mediabox
    assert round(float(box.width)) == 595  # 210 mm
    assert round(float(box.height)) == 842  # 297 mm
    # Still lossless: no JPEG stream.
    assert b"/DCTDecode" not in (tmp_path / artifact.filename).read_bytes()


def test_export_merged_pdf(tmp_path) -> None:
    image = _noisy_text_image()
    first = _make_page(tmp_path, "m1", image)
    second = _make_page(tmp_path, "m2", image)

    artifact = export_merged_pdf(
        [first.image_path, second.image_path],
        str(tmp_path),
        title="Merged check",
    )
    reader = PdfReader(str(tmp_path / artifact.filename))
    assert len(reader.pages) == 2
    assert artifact.page_count == 2


def _seed_service_with_page(tmp_path, job_id: str = "job-x") -> JobService:
    settings.storage_path = str(tmp_path)
    service = JobService()
    now = datetime.now(timezone.utc)
    page_dir = tmp_path / "jobs" / job_id / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(page_dir / "page-1.png"), _noisy_text_image())
    service._jobs[job_id] = Job(
        id=job_id,
        filename=f"{job_id}.mp4",
        processing_mode="screen",
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
                thumbnail_url=f"/artifacts/jobs/{job_id}/pages/page-1.png",
                image_url=f"/artifacts/jobs/{job_id}/pages/page-1.png",
                sharpness_score=0.9,
                segment_start=0.0,
                segment_end=1.0,
                source_frame_index=1,
                source_timestamp=0.1,
                ocr_text="original text",
                ocr_status="ready",
            )
        ],
        export=ExportArtifact(status="ready", filename=f"{job_id}.pdf"),
    )
    return service


def test_update_page_ocr_text_correction(tmp_path) -> None:
    service = _seed_service_with_page(tmp_path)

    response = service.update_page(
        "job-x", "page-1", UpdatePageRequest(ocrText="Corrected by a human.")
    )
    assert response is not None
    page = response.pages[0]
    assert page.ocrText == "Corrected by a human."
    assert page.ocrStatus == "ready"
    assert page.ocrConfidence is None
    assert response.export.status == "idle"

    cleared = service.update_page("job-x", "page-1", UpdatePageRequest(ocrText="   "))
    assert cleared is not None
    assert cleared.pages[0].ocrStatus == "empty"
    assert cleared.pages[0].ocrText is None


def test_merged_export_service(tmp_path) -> None:
    service = _seed_service_with_page(tmp_path, "job-m1")
    now = datetime.now(timezone.utc)
    page_dir = tmp_path / "jobs" / "job-m2" / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(page_dir / "page-1.png"), _noisy_text_image())
    service._jobs["job-m2"] = Job(
        id="job-m2",
        filename="m2.mp4",
        processing_mode="screen",
        status="ready",
        created_at=now,
        updated_at=now,
        pages=[
            Page(
                id="page-1",
                job_id="job-m2",
                order_index=0,
                page_number=1,
                preview_label="Page 1",
                thumbnail_url="/artifacts/jobs/job-m2/pages/page-1.png",
                image_url="/artifacts/jobs/job-m2/pages/page-1.png",
                sharpness_score=0.9,
                segment_start=0.0,
                segment_end=1.0,
                source_frame_index=1,
                source_timestamp=0.1,
            )
        ],
    )

    result = service.export_merged(MergedExportRequest(jobIds=["job-m1", "job-m2"]))
    assert result is not None
    assert result.pageCount == 2
    assert result.jobCount == 2
    exported = tmp_path / "exports" / result.filename
    assert exported.is_file()

    assert service.export_merged(MergedExportRequest(jobIds=["missing"])) is None


def test_camera_color_output_skips_binarization(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    cleaned_ctx = build_pipeline_context("j1", "video.mp4", "camera", camera_output="cleaned")
    color_ctx = build_pipeline_context("j2", "video.mp4", "camera", camera_output="color")
    assert cleaned_ctx.camera_output == "cleaned"
    assert color_ctx.camera_output == "color"
    # Invalid values fall back to the safe default.
    fallback_ctx = build_pipeline_context("j3", "video.mp4", "camera", camera_output="???")
    assert fallback_ctx.camera_output == "cleaned"

    from app.processing.preview import attach_previews
    from tests.test_export_quality import _make_page as make_page

    colorful = np.zeros((220, 180, 3), dtype=np.uint8)
    colorful[:, :, 2] = 200  # strongly red page content
    page = make_page(tmp_path, "color-page", colorful)
    page.selected_frame.image = colorful
    attach_previews([page], context=color_ctx)
    rendered = cv2.imread(page.image_path)
    # Color mode must keep the channels distinct (no grayscale binarization).
    assert int(np.mean(rendered[:, :, 2])) - int(np.mean(rendered[:, :, 0])) > 100


def test_save_jobs_is_atomic_and_cleanup_respects_retention(tmp_path) -> None:
    settings.storage_path = str(tmp_path)
    service = _seed_service_with_page(tmp_path, "job-keep")
    service._save_jobs()
    assert (tmp_path / "jobs_state.json").is_file()
    assert not (tmp_path / "jobs_state.json.tmp").exists()

    # Orphaned upload + job dir are removed on the next startup.
    orphan_upload = tmp_path / "uploads" / "stray.mp4"
    orphan_upload.write_bytes(b"x")
    orphan_dir = tmp_path / "jobs" / "ghost-job"
    orphan_dir.mkdir(parents=True, exist_ok=True)
    (orphan_dir / "junk.png").write_bytes(b"y")

    # An old finished job whose source video should expire under retention.
    old_video = tmp_path / "uploads" / "old.mp4"
    old_video.write_bytes(b"old")
    with_upload = _seed_service_with_page(tmp_path, "job-old")  # fresh instance reloads state
    job = with_upload._jobs["job-old"]
    job.upload_path = str(old_video)
    job.completed_at = datetime.now(timezone.utc) - timedelta(days=40)
    with_upload._save_jobs()

    original_retention = settings.upload_retention_days
    settings.upload_retention_days = 30
    try:
        reloaded = JobService()
    finally:
        settings.upload_retention_days = original_retention

    assert not orphan_upload.exists()
    assert not orphan_dir.exists()
    assert not old_video.exists()
    assert reloaded._jobs["job-old"].upload_path is None
