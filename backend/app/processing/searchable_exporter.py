from __future__ import annotations

import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import img2pdf
from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation

from app.core.settings import settings
from app.processing.ocr import configure_tesseract, sanitize_language
from app.processing.types import SelectedPage

logger = logging.getLogger(__name__)

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]


@dataclass
class SearchableExportArtifact:
    filename: str
    download_url: str | None
    page_count: int


def export_searchable_pdf(
    job_id: str,
    pages: list[SelectedPage],
    output_dir: str,
    *,
    title: str | None = None,
    lang: str | None = None,
) -> SearchableExportArtifact:
    """
    Build a "sandwich" PDF: each page shows the original image with the OCR
    text drawn invisibly on top (PDF text render mode 3), so the document is
    searchable and copyable while looking pixel-identical to the source.
    """
    if not pages:
        raise ValueError("Cannot export a searchable PDF with no pages.")
    if pytesseract is None:
        raise RuntimeError("pytesseract is not installed. Run: pip install pytesseract")
    configure_tesseract()

    missing = [page.page_id for page in pages if not Path(page.image_path).is_file()]
    if missing:
        raise ValueError(f"Page image(s) missing for export: {', '.join(missing)}")

    language = sanitize_language(lang)
    workers = min(max(1, min(4, os.cpu_count() or 2)), len(pages))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vid2pdf-spdf") as pool:
        page_pdfs = list(
            pool.map(lambda page: _page_to_pdf_layers(page.image_path, language), pages)
        )

    writer = PdfWriter()
    for image_path, image_pdf, text_pdf in page_pdfs:
        base_page = PdfReader(io.BytesIO(image_pdf)).pages[0]
        # Attach to the writer first, then merge the text layer onto the
        # writer's own page (merging reader pages is deprecated in pypdf).
        writer_page = writer.add_page(base_page)
        if text_pdf is None:
            continue
        try:
            text_page = PdfReader(io.BytesIO(text_pdf)).pages[0]
            scale_x = float(writer_page.mediabox.width) / max(
                float(text_page.mediabox.width), 1e-6
            )
            scale_y = float(writer_page.mediabox.height) / max(
                float(text_page.mediabox.height), 1e-6
            )
            writer_page.merge_transformed_page(
                text_page,
                Transformation().scale(scale_x, scale_y),
            )
        except Exception:
            # An unreadable text layer should never block the export; the
            # page simply stays image-only (still pixel-perfect).
            logger.warning("Could not merge OCR text layer for %s", image_path, exc_info=True)
    writer.add_metadata(
        {
            "/Title": title or f"Vid2PDF export {job_id}",
            "/Creator": "Vid2PDF",
        }
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filename = f"{job_id}-searchable.pdf"
    file_path = output_path / filename
    with open(file_path, "wb") as fh:
        writer.write(fh)

    logger.info(
        "Searchable PDF written for job=%s: pages=%s, lang=%s, bytes=%s",
        job_id,
        len(pages),
        language,
        file_path.stat().st_size,
    )
    return SearchableExportArtifact(
        filename=filename,
        download_url=None,
        page_count=len(pages),
    )


def _page_to_pdf_layers(image_path: str, language: str) -> tuple[str, bytes, bytes | None]:
    """Produce the lossless image PDF and Tesseract's invisible text overlay.

    Tesseract's own sandwich PDF re-encodes the image as JPEG, which visibly
    degraded exports. Instead we embed the page image losslessly with img2pdf
    and ask Tesseract only for the text overlay (textonly_pdf=1); the caller
    merges the two, scaling the overlay to the image page.
    """
    text_pdf: bytes | None
    try:
        with Image.open(image_path) as image:
            text_pdf = pytesseract.image_to_pdf_or_hocr(
                image.convert("RGB"),
                extension="pdf",
                lang=language,
                config=f"--oem {settings.ocr_oem} --psm {settings.ocr_psm} -c textonly_pdf=1",
            )
    except Exception:
        logger.warning("OCR text layer failed for %s", image_path, exc_info=True)
        text_pdf = None

    image_pdf = img2pdf.convert(image_path)
    return image_path, image_pdf, text_pdf
