from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.processing.types import SelectedPage


@dataclass
class ExportArtifact:
    filename: str
    download_url: str | None
    page_count: int


def export_pdf(job_id: str, pages: list[SelectedPage], output_dir: str) -> ExportArtifact:
    if not pages:
        raise ValueError("Cannot export a PDF with no pages.")

    missing = [page.page_id for page in pages if not Path(page.image_path).is_file()]
    if missing:
        raise ValueError(f"Page image(s) missing for export: {', '.join(missing)}")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filename = f"{job_id}.pdf"
    file_path = output_path / filename

    images = [Image.open(page.image_path).convert("RGB") for page in pages]
    try:
        images[0].save(
            file_path,
            save_all=True,
            append_images=images[1:],
            resolution=150,
        )
    finally:
        for image in images:
            image.close()

    return ExportArtifact(filename=filename, download_url=None, page_count=len(pages))
