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
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filename = f"{job_id}.pdf"
    file_path = output_path / filename

    first_page = None
    page_images = []
    for index, page in enumerate(pages):
        image = Image.open(page.image_path).convert("RGB")
        if page.rotation:
            image = image.rotate(-page.rotation, expand=True, fillcolor="white")
        if index == 0:
            first_page = image
        else:
            page_images.append(image)

    if not pages or first_page is None:
        raise ValueError("Cannot export a PDF with no pages.")

    first_page.save(
        file_path,
        save_all=True,
        append_images=page_images,
        resolution=150,
    )
    return ExportArtifact(filename=filename, download_url=None, page_count=len(pages))
