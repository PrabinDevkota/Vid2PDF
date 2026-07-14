from __future__ import annotations

import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter

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
            pool.map(lambda page: _page_to_searchable_pdf(page.image_path, language), pages)
        )

    writer = PdfWriter()
    for page_pdf in page_pdfs:
        reader = PdfReader(io.BytesIO(page_pdf))
        for pdf_page in reader.pages:
            writer.add_page(pdf_page)
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


def _page_to_searchable_pdf(image_path: str, language: str) -> bytes:
    """Tesseract's PDF renderer: original image + invisible text layer."""
    with Image.open(image_path) as image:
        return pytesseract.image_to_pdf_or_hocr(
            image.convert("RGB"),
            extension="pdf",
            lang=language,
            config=f"--oem {settings.ocr_oem} --psm {settings.ocr_psm}",
        )
