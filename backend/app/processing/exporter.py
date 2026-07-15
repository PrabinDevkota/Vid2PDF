from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import img2pdf
from PIL import Image

from app.processing.types import SelectedPage

# Page dimensions in millimetres.
_PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "a4": (210.0, 297.0),
    "letter": (215.9, 279.4),
}
_MARGIN_MM: dict[str, float] = {"none": 0.0, "small": 10.0}


@dataclass
class ExportArtifact:
    filename: str
    download_url: str | None
    page_count: int


def _layout_fun(page_size: str, margin: str):
    """img2pdf layout for a fixed paper size, or None for image-sized pages."""
    dimensions = _PAGE_SIZES_MM.get(page_size)
    if dimensions is None:
        return None
    border_mm = _MARGIN_MM.get(margin, 0.0)
    border = (img2pdf.mm_to_pt(border_mm), img2pdf.mm_to_pt(border_mm)) if border_mm else None
    return img2pdf.get_layout_fun(
        pagesize=(img2pdf.mm_to_pt(dimensions[0]), img2pdf.mm_to_pt(dimensions[1])),
        border=border,
        fit=img2pdf.FitMode.into,
    )


def _write_pdf(
    file_path: Path,
    image_paths: list[str],
    *,
    title: str,
    page_size: str = "auto",
    margin: str = "none",
) -> None:
    """Losslessly embed the images (Flate for PNG sources) into one PDF."""
    kwargs: dict = {"title": title, "creator": "Vid2PDF"}
    layout = _layout_fun(page_size, margin)
    if layout is not None:
        kwargs["layout_fun"] = layout
    with open(file_path, "wb") as fh:
        fh.write(img2pdf.convert(image_paths, **kwargs))


def export_pdf(
    job_id: str,
    pages: list[SelectedPage],
    output_dir: str,
    *,
    title: str | None = None,
    page_size: str = "auto",
    margin: str = "none",
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
        _write_pdf(
            file_path,
            [str(page.image_path) for page in pages],
            title=document_title,
            page_size=page_size,
            margin=margin,
        )
    except Exception:
        # Defensive fallback (e.g. an image img2pdf refuses): Pillow's PDF
        # writer JPEG-encodes pages; force high quality instead of default 75.
        _export_pdf_pillow(file_path, pages, document_title)

    return ExportArtifact(filename=filename, download_url=None, page_count=len(pages))


def export_merged_pdf(
    image_paths: list[str],
    output_dir: str,
    *,
    title: str,
    page_size: str = "auto",
    margin: str = "none",
) -> ExportArtifact:
    """Combine pages from several jobs into a single lossless PDF."""
    if not image_paths:
        raise ValueError("Cannot export a merged PDF with no pages.")
    missing = [path for path in image_paths if not Path(path).is_file()]
    if missing:
        raise ValueError(f"Page image(s) missing for merged export: {len(missing)} file(s)")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"merged-{stamp}.pdf"
    _write_pdf(
        output_path / filename,
        image_paths,
        title=title,
        page_size=page_size,
        margin=margin,
    )
    return ExportArtifact(filename=filename, download_url=None, page_count=len(image_paths))


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
