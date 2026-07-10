from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

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
        image = Image.open(path)
        data = pytesseract.image_to_data(
            image,
            lang=settings.ocr_language,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:  # pragma: no cover - depends on system tesseract
        logger.exception("OCR failed for page %s", page_id)
        return PageText(
            page_id=page_id,
            page_number=page_number,
            status="failed",
            error=f"OCR failed: {exc}",
        )

    blocks = _blocks_from_tesseract_data(data)
    raw_text = _join_blocks(blocks)
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
    # Join hyphenated line breaks: "exam-\nple" -> "example"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Normalize newlines to spaces within paragraphs, keep blank-line breaks
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
        if conf < settings.ocr_min_confidence:
            continue

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
        line_text = " ".join(word for _, word, _, _, _ in words)
        line_text = normalize_ocr_text(line_text)
        if not line_text:
            continue
        confidences = [conf for _, _, conf, _, _ in words]
        avg_conf = sum(confidences) / len(confidences)
        top = min(item[3] for item in words)
        left = min(item[4] for item in words)
        blocks.append(
            TextBlock(text=line_text, confidence=avg_conf, top=top, left=left)
        )

    # Reading order: top-to-bottom, then left-to-right
    blocks.sort(key=lambda block: (block.top, block.left))
    return blocks


def _join_blocks(blocks: list[TextBlock]) -> str:
    if not blocks:
        return ""
    # Group nearby lines into paragraphs by vertical gap
    paragraphs: list[list[str]] = []
    current: list[str] = []
    previous_top: int | None = None
    for block in blocks:
        if previous_top is not None and block.top - previous_top > 28 and current:
            paragraphs.append(current)
            current = []
        current.append(block.text)
        previous_top = block.top
    if current:
        paragraphs.append(current)
    return "\n\n".join(" ".join(lines) for lines in paragraphs)
