from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageOps

from app.core.settings import settings

logger = logging.getLogger(__name__)

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]


@dataclass
class TextBlock:
    text: str
    confidence: float
    top: int
    left: int


@dataclass
class PageText:
    page_id: str
    page_number: int
    blocks: list[TextBlock] = field(default_factory=list)
    raw_text: str = ""
    status: str = "ready"  # ready | empty | failed
    error: str | None = None


def resolve_tesseract_cmd() -> str:
    """Resolve the Tesseract binary even if the process PATH is stale."""
    candidates: list[str] = []
    if settings.tesseract_cmd:
        candidates.append(settings.tesseract_cmd)

    which = shutil.which("tesseract")
    if which:
        candidates.append(which)

    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates.extend(
        [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            str(local_app_data / "Programs" / "Tesseract-OCR" / "tesseract.exe"),
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if path.is_file():
            return str(path.resolve())
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    raise RuntimeError(
        "Tesseract OCR binary was not found. "
        "Install Tesseract (https://github.com/UB-Mannheim/tesseract/wiki) "
        "or set settings.tesseract_cmd to the full path of tesseract.exe."
    )


def configure_tesseract() -> None:
    if pytesseract is None:
        raise RuntimeError(
            "pytesseract is not installed. Run: pip install pytesseract"
        )
    tesseract_path = resolve_tesseract_cmd()
    pytesseract.pytesseract.tesseract_cmd = tesseract_path


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """OCR-friendly preprocess: grayscale, upscale, CLAHE/autocontrast, light denoise."""
    if not settings.ocr_preprocess_enabled:
        return image.convert("RGB")

    rgb = image.convert("RGB")
    width, height = rgb.size
    min_width = settings.ocr_upscale_min_width
    if width < min_width:
        scale = min_width / max(width, 1)
        rgb = rgb.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.LANCZOS,
        )

    gray = ImageOps.grayscale(rgb)
    array = np.array(gray)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(array)
    denoised = cv2.fastNlMeansDenoising(enhanced, None, 8, 7, 21)
    result = Image.fromarray(denoised)
    result = ImageOps.autocontrast(result)
    result = result.filter(ImageFilter.MedianFilter(size=3))
    return result.convert("RGB")


def extract_page_text(
    image_path: str,
    *,
    page_id: str,
    page_number: int,
) -> PageText:
    """OCR a single page image into ordered text blocks."""
    try:
        configure_tesseract()
    except RuntimeError as exc:
        return PageText(
            page_id=page_id,
            page_number=page_number,
            status="failed",
            error=str(exc),
        )

    path = Path(image_path)
    if not path.exists():
        return PageText(
            page_id=page_id,
            page_number=page_number,
            status="failed",
            error=f"Page image not found: {image_path}",
        )

    try:
        original = Image.open(path)
        processed = preprocess_for_ocr(original)
        primary = _ocr_pass(processed, psm=settings.ocr_psm)
        blocks = primary["blocks"]
        raw_text = primary["raw_text"]
        string_text = primary["string_text"]

        if len(raw_text.strip()) < 40:
            fallback = _ocr_pass(processed, psm=settings.ocr_psm_fallback)
            if len(fallback["raw_text"].strip()) > len(raw_text.strip()):
                blocks = fallback["blocks"]
                raw_text = fallback["raw_text"]
                string_text = fallback["string_text"]

        # Prefer longer plain string dump when structured OCR lost too much text.
        if len(string_text.strip()) > len(raw_text.strip()) * 1.25:
            raw_text = normalize_ocr_text(string_text)
            if not blocks:
                blocks = [
                    TextBlock(text=part, confidence=70.0, top=index * 30, left=0)
                    for index, part in enumerate(raw_text.split("\n\n"))
                    if part.strip()
                ]
    except Exception as exc:  # pragma: no cover - depends on system tesseract
        logger.exception("OCR failed for page %s", page_id)
        return PageText(
            page_id=page_id,
            page_number=page_number,
            status="failed",
            error=f"OCR failed: {exc}",
        )

    if not raw_text.strip():
        return PageText(
            page_id=page_id,
            page_number=page_number,
            blocks=[],
            raw_text="",
            status="empty",
        )

    return PageText(
        page_id=page_id,
        page_number=page_number,
        blocks=blocks,
        raw_text=raw_text,
        status="ready",
    )


def normalize_ocr_text(text: str) -> str:
    """Within-page cleanup: whitespace collapse and hyphenated line breaks."""
    if not text:
        return ""
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    parts = re.split(r"\n\s*\n", text)
    cleaned_parts = []
    for part in parts:
        line = re.sub(r"[ \t]+", " ", part)
        line = re.sub(r"\n+", " ", line).strip()
        if line:
            cleaned_parts.append(line)
    return "\n\n".join(cleaned_parts)


def text_similarity(left: str, right: str) -> float:
    a = re.sub(r"\s+", " ", left).strip().lower()
    b = re.sub(r"\s+", " ", right).strip().lower()
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def find_consecutive_near_duplicates(
    pages: list[PageText],
    threshold: float | None = None,
) -> list[tuple[str, str, float]]:
    """Return (page_id_a, page_id_b, similarity) for consecutive near-duplicates."""
    limit = threshold if threshold is not None else settings.ocr_consecutive_duplicate_similarity
    flags: list[tuple[str, str, float]] = []
    for index in range(1, len(pages)):
        previous = pages[index - 1]
        current = pages[index]
        if previous.status != "ready" or current.status != "ready":
            continue
        score = text_similarity(previous.raw_text, current.raw_text)
        if score >= limit:
            flags.append((previous.page_id, current.page_id, score))
    return flags


def _ocr_pass(image: Image.Image, *, psm: int) -> dict:
    config = f"--oem {settings.ocr_oem} --psm {psm}"
    data = pytesseract.image_to_data(
        image,
        lang=settings.ocr_language,
        config=config,
        output_type=pytesseract.Output.DICT,
    )
    blocks = _blocks_from_tesseract_data(data)
    raw_text = _join_blocks(blocks)
    string_text = pytesseract.image_to_string(
        image,
        lang=settings.ocr_language,
        config=config,
    )
    return {
        "blocks": blocks,
        "raw_text": raw_text,
        "string_text": string_text,
    }


def _blocks_from_tesseract_data(data: dict) -> list[TextBlock]:
    """Group Tesseract word rows into reading-order line blocks."""
    n = len(data.get("text", []))
    lines: dict[tuple[int, int, int], list[tuple[int, str, float, int, int]]] = {}

    for index in range(n):
        text = (data["text"][index] or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][index])
        except (TypeError, ValueError):
            conf = -1.0
        # Only drop unknown confidence; keep low-confidence words for recall.
        if conf < 0:
            continue
        if conf < settings.ocr_min_confidence:
            # Soft filter: keep if above absolute floor of 0
            pass

        key = (
            int(data["block_num"][index]),
            int(data["par_num"][index]),
            int(data["line_num"][index]),
        )
        left = int(data["left"][index])
        top = int(data["top"][index])
        lines.setdefault(key, []).append((left, text, conf, top, left))

    blocks: list[TextBlock] = []
    for key in sorted(lines.keys()):
        words = sorted(lines[key], key=lambda item: item[0])
        # Prefer keeping low-conf words when the line average is decent
        confidences = [conf for _, _, conf, _, _ in words]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        kept_words = [
            word
            for _, word, conf, _, _ in words
            if conf >= settings.ocr_min_confidence or avg_conf >= settings.ocr_min_confidence
        ]
        if not kept_words:
            kept_words = [word for _, word, _, _, _ in words]
        line_text = normalize_ocr_text(" ".join(kept_words))
        if not line_text:
            continue
        top = min(item[3] for item in words)
        left = min(item[4] for item in words)
        blocks.append(
            TextBlock(text=line_text, confidence=avg_conf, top=top, left=left)
        )

    blocks.sort(key=lambda block: (block.top, block.left))
    return blocks


def _join_blocks(blocks: list[TextBlock]) -> str:
    if not blocks:
        return ""
    heights = [
        max(8, abs(blocks[index].top - blocks[index - 1].top))
        for index in range(1, len(blocks))
    ]
    median_gap = float(np.median(heights)) if heights else 28.0
    paragraph_gap = max(18.0, median_gap * 1.5)

    paragraphs: list[list[str]] = []
    current: list[str] = []
    previous_top: int | None = None
    for block in blocks:
        if previous_top is not None and block.top - previous_top > paragraph_gap and current:
            paragraphs.append(current)
            current = []
        current.append(block.text)
        previous_top = block.top
    if current:
        paragraphs.append(current)
    return "\n\n".join(" ".join(lines) for lines in paragraphs)
