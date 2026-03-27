from pathlib import Path

from app.core.settings import settings
from app.processing.types import PipelineContext


def build_pipeline_context(job_id: str, upload_path: str, processing_mode: str) -> PipelineContext:
    job_root = Path(settings.storage_path) / "jobs" / job_id
    page_dir = job_root / "pages"
    thumbnail_dir = job_root / "thumbnails"
    debug_dir = job_root / "debug"
    debug_report_path = debug_dir / "pipeline_report.json"
    return PipelineContext(
        job_id=job_id,
        upload_path=upload_path,
        job_root=str(job_root),
        page_dir=str(page_dir),
        thumbnail_dir=str(thumbnail_dir),
        debug_dir=str(debug_dir),
        debug_report_path=str(debug_report_path),
        artifact_base_url=settings.public_artifact_base_url,
        processing_mode=processing_mode,  # type: ignore[arg-type]
    )
