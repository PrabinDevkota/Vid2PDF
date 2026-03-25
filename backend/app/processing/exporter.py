from dataclasses import dataclass

from app.processing.types import SelectedPage


@dataclass
class ExportArtifact:
    filename: str
    download_url: str | None
    page_count: int


def export_pdf(job_id: str, pages: list[SelectedPage]) -> ExportArtifact:
    """Placeholder PDF export boundary."""
    return ExportArtifact(
        filename=f"{job_id}.pdf",
        download_url=None,
        page_count=len(pages),
    )
