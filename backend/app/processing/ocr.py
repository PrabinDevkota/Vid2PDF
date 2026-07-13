from __future__ import annotations

import logging
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.core.settings import settings

logger = logging.getLogger(__name__)

# Prefer many single-threaded Tesseract processes over OpenMP oversubscription.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]

_VOWELS = set("aeiouyAEIOUY")
_GIBBERISH_TOKEN = re.compile(
    r"^(?:[^\w]|ee+|ss+|se+|oe+|we+|sc+|ps+|[_=>\-]+)+$",
    re.IGNORECASE,
)
_TESSERACT_CONFIGURED = False


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
    global _TESSERACT_CONFIGURED
    if pytesseract is None:
        raise RuntimeError(
            "pytesseract is not installed. Run: pip install pytesseract"
        )
    if _TESSERACT_CONFIGURED and pytesseract.pytesseract.tesseract_cmd:
        return
    tesseract_path = resolve_tesseract_cmd()
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
    _TESSERACT_CONFIGURED = True


def preprocess_for_ocr(image: Image.Image, *, variant: str = "clahe") -> Image.Image:
    """OCR-friendly preprocess variants: CLAHE (default), adaptive binary, or Otsu."""
    if not settings.ocr_preprocess_enabled:
        return image.convert("RGB")

    rgb = image.convert("RGB")
    width, height = rgb.size
    min_width = settings.ocr_upscale_min_width
    if width < min_width:
        scale = min_width / max(width, 1)
        # BILINEAR is much faster than LANCZOS and good enough for OCR upscales.
        rgb = rgb.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.BILINEAR,
        )

    gray = ImageOps.grayscale(rgb)
    array = np.array(gray)
    if settings.ocr_deskew_enabled:
        array = _deskew_gray(array)

    if variant == "adaptive":
        blurred = cv2.GaussianBlur(array, (3, 3), 0)
        binary = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        return Image.fromarray(binary).convert("RGB")

    if variant == "otsu":
        blurred = cv2.GaussianBlur(array, (3, 3), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return Image.fromarray(binary).convert("RGB")

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(array)
    if settings.ocr_denoise_enabled:
        enhanced = cv2.fastNlMeansDenoising(enhanced, None, 7, 7, 21)
    else:
        enhanced = cv2.GaussianBlur(enhanced, (3, 3), 0)
    result = Image.fromarray(enhanced)
    result = ImageOps.autocontrast(result)
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
        best = _best_ocr_result(original)
        blocks = best["blocks"]
        raw_text = best["raw_text"]
    except Exception as exc:  # pragma: no cover - depends on system tesseract
        logger.exception("OCR failed for page %s", page_id)
        return PageText(
            page_id=page_id,
            page_number=page_number,
            status="failed",
            error=f"OCR failed: {exc}",
        )

    if not raw_text.strip() or not is_plausible_page_text(raw_text):
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


def extract_pages_text_parallel(
    jobs: list[tuple[str, str, int]],
) -> list[PageText]:
    """
    OCR many pages in parallel.

    Each job is (image_path, page_id, page_number). Results are returned in the
    same order as `jobs`.
    """
    if not jobs:
        return []
    if len(jobs) == 1:
        image_path, page_id, page_number = jobs[0]
        return [extract_page_text(image_path, page_id=page_id, page_number=page_number)]

    workers = settings.ocr_workers
    if workers <= 0:
        workers = min(4, max(1, (os.cpu_count() or 2)))
    workers = min(workers, len(jobs))

    results: list[PageText | None] = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vid2pdf-ocr") as pool:
        futures = {
            pool.submit(
                extract_page_text,
                image_path,
                page_id=page_id,
                page_number=page_number,
            ): index
            for index, (image_path, page_id, page_number) in enumerate(jobs)
        }
        for future in as_completed(futures):
            index = futures[future]
            results[index] = future.result()

    return [
        item
        if item is not None
        else PageText(
            page_id="unknown",
            page_number=index + 1,
            status="failed",
            error="OCR worker returned no result",
        )
        for index, item in enumerate(results)
    ]


_CHAR_NORMALIZATIONS = str.maketrans(
    {
        "�": None,  # U+FFFD replacement char from failed decodes
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
    }
)


def normalize_ocr_text(text: str) -> str:
    """Within-page cleanup: whitespace collapse and hyphenated line breaks."""
    if not text:
        return ""
    text = text.translate(_CHAR_NORMALIZATIONS)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    parts = re.split(r"\n\s*\n", text)
    cleaned_parts = []
    for part in parts:
        line = re.sub(r"[ \t]+", " ", part)
        line = re.sub(r"\n+", " ", line).strip()
        line = clean_gibberish_text(line)
        if line:
            cleaned_parts.append(line)
    return "\n\n".join(cleaned_parts)


def clean_gibberish_text(text: str) -> str:
    """Drop nonsense OCR tokens while keeping readable words."""
    if not text:
        return ""
    tokens = text.split()
    kept: list[str] = []
    for token in tokens:
        if _is_plausible_token(token):
            kept.append(token)
    return " ".join(kept).strip()


def is_plausible_page_text(text: str) -> bool:
    """Reject pages that are mostly OCR noise."""
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) < 8:
        return False
    tokens = [token for token in compact.split() if token]
    if not tokens:
        return False
    plausible = sum(1 for token in tokens if _is_plausible_token(token))
    ratio = plausible / len(tokens)
    if ratio < settings.ocr_min_plausible_ratio:
        return False
    letters = [char for char in compact if char.isalpha()]
    if len(letters) < 6:
        return False
    vowel_ratio = sum(1 for char in letters if char in _VOWELS) / len(letters)
    return vowel_ratio >= 0.18


def _distinctive_tokens(text: str) -> set[str]:
    """Tokens that survive OCR garbling: real words (>=4 chars) and numbers."""
    tokens: set[str] = set()
    for token in re.findall(r"[a-z]{4,}|\d+", text.lower()):
        tokens.add(token)
    return tokens


def token_set_similarity(left: str, right: str) -> float:
    """Jaccard overlap of distinctive tokens; robust to garbled duplicates."""
    left_tokens = _distinctive_tokens(left)
    right_tokens = _distinctive_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return overlap / union


def _is_duplicate_ocr_text(left: str, right: str, sequence_limit: float) -> bool:
    if text_similarity(left, right) >= sequence_limit:
        return True
    # Garbled duplicates: character-level similarity collapses under OCR noise,
    # but the distinctive words/numbers of the same page still overlap heavily.
    left_tokens = _distinctive_tokens(left)
    right_tokens = _distinctive_tokens(right)
    if (
        len(left_tokens) < settings.ocr_duplicate_min_distinctive_tokens
        or len(right_tokens) < settings.ocr_duplicate_min_distinctive_tokens
    ):
        return False
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return overlap >= settings.ocr_duplicate_token_overlap


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
        if score >= limit or _is_duplicate_ocr_text(previous.raw_text, current.raw_text, limit):
            score = max(score, token_set_similarity(previous.raw_text, current.raw_text))
            flags.append((previous.page_id, current.page_id, score))
    return flags


def collapse_ocr_duplicate_pages(
    pages: list,
    ocr_results: list[PageText],
    *,
    threshold: float | None = None,
) -> tuple[list, list[PageText], int]:
    """
    Remove near-duplicate pages using OCR text similarity (any distance).
    Keeps the higher-quality / higher-confidence page of each cluster.
    """
    if len(pages) != len(ocr_results) or len(pages) < 2:
        return pages, ocr_results, 0

    limit = threshold if threshold is not None else settings.ocr_global_duplicate_similarity
    keep = [True] * len(pages)
    removed = 0

    for index in range(len(pages)):
        if not keep[index]:
            continue
        for other in range(index + 1, len(pages)):
            if not keep[other]:
                continue
            left = ocr_results[index]
            right = ocr_results[other]
            if left.status != "ready" or right.status != "ready":
                continue
            if len(left.raw_text.strip()) < 24 or len(right.raw_text.strip()) < 24:
                continue
            if not _is_duplicate_ocr_text(left.raw_text, right.raw_text, limit):
                continue
            drop = other if _ocr_page_rank(left, pages[index]) >= _ocr_page_rank(right, pages[other]) else index
            if keep[drop]:
                keep[drop] = False
                removed += 1
            if not keep[index]:
                break

    filtered_pages = [page for index, page in enumerate(pages) if keep[index]]
    filtered_ocr = [item for index, item in enumerate(ocr_results) if keep[index]]
    for index, (page, ocr) in enumerate(zip(filtered_pages, filtered_ocr), start=1):
        # Keep stable page_id so preview/image artifact paths remain valid.
        page.page_number = index
        page.label = f"Page {index}"
        ocr.page_number = index
        ocr.page_id = page.page_id
    return filtered_pages, filtered_ocr, removed


def _ocr_page_rank(ocr: PageText, page) -> float:
    confidence = 0.0
    if ocr.blocks:
        confidence = sum(block.confidence for block in ocr.blocks) / len(ocr.blocks)
    quality = 0.0
    try:
        quality = float(page.selected_frame.quality.score)
    except Exception:
        quality = 0.0
    return confidence + (quality * 40.0) + min(len(ocr.raw_text), 800) * 0.02


def _best_ocr_result(original: Image.Image) -> dict:
    """
    Fast cascade: one good pass usually wins; only escalate when quality is poor.

    Typical path: 1 Tesseract call. Worst path: a few targeted fallbacks
    (not a full 3×3 grid of preprocess × PSM).
    """
    primary_psms = list(settings.ocr_psm_candidates) or [settings.ocr_psm]
    fallback_psms = list(settings.ocr_psm_fallback_candidates) or [settings.ocr_psm_fallback]
    accept_score = settings.ocr_fast_accept_score

    best: dict | None = None
    best_score = -1.0

    # Pass 1: fast CLAHE + primary PSM(s)
    clahe = preprocess_for_ocr(original, variant="clahe")
    for psm in primary_psms:
        candidate = _ocr_pass(clahe, psm=psm)
        score = _score_ocr_candidate(candidate)
        if score > best_score:
            best_score = score
            best = candidate
        if best_score >= accept_score:
            return best

    # Pass 2: alternate PSM on the same preprocess (cheap — image already ready)
    for psm in fallback_psms:
        if psm in primary_psms:
            continue
        candidate = _ocr_pass(clahe, psm=psm)
        score = _score_ocr_candidate(candidate)
        if score > best_score:
            best_score = score
            best = candidate
        if best_score >= accept_score:
            return best

    # Pass 3: only if still weak — try binary variants with primary PSM
    if best_score < accept_score:
        for variant in ("adaptive", "otsu"):
            processed = preprocess_for_ocr(original, variant=variant)
            candidate = _ocr_pass(processed, psm=primary_psms[0])
            score = _score_ocr_candidate(candidate)
            if score > best_score:
                best_score = score
                best = candidate
            if best_score >= accept_score:
                break

    assert best is not None
    return best


def _score_ocr_candidate(candidate: dict) -> float:
    raw = candidate.get("raw_text") or ""
    blocks: list[TextBlock] = candidate.get("blocks") or []
    if not raw.strip():
        return 0.0
    plausible = 1.0 if is_plausible_page_text(raw) else 0.15
    avg_conf = (
        sum(block.confidence for block in blocks) / len(blocks) if blocks else 20.0
    )
    length_bonus = min(len(raw.strip()), 1200) / 1200.0
    return (avg_conf * 0.55) + (plausible * 35.0) + (length_bonus * 20.0)


def _ocr_pass(image: Image.Image, *, psm: int) -> dict:
    """Single Tesseract invocation via image_to_data (no duplicate image_to_string)."""
    config = f"--oem {settings.ocr_oem} --psm {psm}"
    data = pytesseract.image_to_data(
        image,
        lang=settings.ocr_language,
        config=config,
        output_type=pytesseract.Output.DICT,
    )
    blocks = _blocks_from_tesseract_data(data)
    raw_text = _join_blocks(blocks)
    return {
        "blocks": blocks,
        "raw_text": raw_text,
        "string_text": raw_text,
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
        if conf < 0:
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
        confidences = [conf for _, _, conf, _, _ in words]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        kept_words = [
            word
            for _, word, conf, _, _ in words
            if (
                conf >= settings.ocr_min_confidence
                or (conf >= settings.ocr_soft_confidence and avg_conf >= settings.ocr_min_confidence)
            )
            and _is_plausible_token(word)
        ]
        if not kept_words and avg_conf >= settings.ocr_min_confidence:
            kept_words = [
                word
                for _, word, conf, _, _ in words
                if conf >= settings.ocr_soft_confidence and _is_plausible_token(word)
            ]
        if not kept_words:
            continue
        if avg_conf < settings.ocr_min_confidence:
            # Low-confidence lines are kept only when they mostly read as words;
            # this drops fragment lines like "4 on . SY 5 4 /".
            plausible_count = sum(
                1 for _, word, _, _, _ in words if _is_plausible_token(word)
            )
            if plausible_count < len(words) / 2:
                continue
        line_text = normalize_ocr_text(" ".join(kept_words))
        if not line_text:
            continue
        # Keep short headings; drop longer lines that are mostly noise.
        if len(line_text) >= 40 and not is_plausible_page_text(line_text):
            continue
        if not any(_is_plausible_token(token) for token in line_text.split()):
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
    # Slightly looser paragraph gap so book lines merge into flowing paragraphs.
    paragraph_gap = max(22.0, median_gap * 1.85)

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


def _is_plausible_token(token: str) -> bool:
    cleaned = re.sub(r"^[^\w]+|[^\w]+$", "", token)
    # Keep standalone currency/math punctuation that appears in real prose.
    if token in {"&", "%", "$", "#", "+", "=", "/", ":", ";"}:
        return True
    if not cleaned:
        return bool(re.fullmatch(r"[\w&%$#+\-/=:;.]+", token))
    if len(cleaned) == 1 and cleaned.isalpha():
        return cleaned.lower() in set("aio")
    if _GIBBERISH_TOKEN.match(cleaned):
        return False
    letters = [char for char in cleaned if char.isalpha()]
    if not letters:
        # Keep short numbers / punctuation-light tokens.
        return bool(re.fullmatch(r"[\d$%.,:+\-/]+", cleaned)) and len(cleaned) <= 12
    if len(letters) >= 4:
        unique_ratio = len(set(char.lower() for char in letters)) / len(letters)
        if unique_ratio < 0.28:
            return False
        vowel_count = sum(1 for char in letters if char in _VOWELS)
        if vowel_count == 0:
            # Vowel-less words are usually OCR noise, but short all-caps
            # acronyms (HTTP, XML, PDF...) are legitimate prose.
            if not (cleaned.isalpha() and cleaned.isupper() and len(cleaned) <= 6):
                return False
    # Reject long runs of the same character (eeeee, SSSSS).
    if re.search(r"(.)\1{3,}", cleaned, flags=re.IGNORECASE):
        return False
    return True


def _deskew_gray(gray: np.ndarray) -> np.ndarray:
    """Light deskew using text-pixel minAreaRect; no-op on failure."""
    try:
        # Downsample for angle estimation — much faster on large pages.
        height, width = gray.shape[:2]
        work = gray
        if max(height, width) > 900:
            scale = 900 / max(height, width)
            work = cv2.resize(
                gray,
                (max(1, int(width * scale)), max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        binary = cv2.threshold(work, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(binary > 0))
        if coords.shape[0] < 200:
            return gray
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 0.5 or abs(angle) > 12:
            return gray
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        return cv2.warpAffine(
            gray,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
    except Exception:  # pragma: no cover
        return gray
