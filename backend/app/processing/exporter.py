from dataclasses import dataclass
from pathlib import Path

import img2pdf
from PIL import Image

from app.processing.types import SelectedPage


@dataclass
class ExportArtifact:
    filename: str
    download_url: str | None
    page_count: int


def export_pdf(
    job_id: str,
    pages: list[SelectedPage],
    output_dir: str,
    *,
    title: str | None = None,
) -> ExportArtifact:
    if not pages:
        raise ValueError("Cannot export a PDF with no pages.")

    missing = [page.page_id for page in pages if not Path(page.image_path).is_file()]
    if missing:
        raise ValueError(f"Page image(s) missing for export: {', '.join(missing)}")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filename = f"{job_id}.pdf"
    file_path = output_path / filename
    document_title = title or f"Vid2PDF export {job_id}"

    try:
        # img2pdf embeds the page images losslessly (Flate for PNG sources),
        # so the PDF is pixel-identical to the reviewed pages.
        with open(file_path, "wb") as fh:
            fh.write(
                img2pdf.convert(
                    [str(page.image_path) for page in pages],
                    title=document_title,
                    creator="Vid2PDF",
                )
            )
    except Exception:
        # Defensive fallback (e.g. an image img2pdf refuses): Pillow's PDF
        # writer JPEG-encodes pages; force high quality instead of default 75.
        _export_pdf_pillow(file_path, pages, document_title)

    return ExportArtifact(filename=filename, download_url=None, page_count=len(pages))


def _export_pdf_pillow(file_path: Path, pages: list[SelectedPage], title: str) -> None:
    images = [Image.open(page.image_path).convert("RGB") for page in pages]
    try:
        images[0].save(
            file_path,
            save_all=True,
            append_images=images[1:],
            resolution=150,
            quality=95,
            title=title,
            creator="Vid2PDF",
        )
    finally:
        for image in images:
            image.close()
