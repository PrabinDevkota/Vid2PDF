from __future__ import annotations

import logging
import re
import shutil
from difflib import SequenceMatcher

import cv2
import numpy as np

from app.core.settings import settings
from app.processing.document import normalize_final_page
from app.processing.types import SelectedPage

logger = logging.getLogger(__name__)

try:
    import pytesseract  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    pytesseract = None


def remove_duplicates(
    pages: list[SelectedPage],
    max_hamming_distance: int = 6,
) -> list[SelectedPage]:
    unique_pages: list[SelectedPage] = []
    removed_count = 0

    for page in sorted(pages, key=lambda item: item.segment_start):
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(unique_pages)
                if _is_duplicate_candidate(page, existing, max_hamming_distance)
            ),
            None,
        )
        if duplicate_index is None:
            unique_pages.append(page)
            continue

        removed_count += 1
        if _page_quality_rank(page) > _page_quality_rank(unique_pages[duplicate_index]):
            unique_pages[duplicate_index] = page

    for index, page in enumerate(unique_pages, start=1):
        page.page_number = index
        page.label = f"Page {index}"
        page.page_id = f"page-{index}"

    logger.info(
        "Deduplication complete: input_pages=%s, kept_pages=%s, removed_pages=%s, max_hamming_distance=%s",
        len(pages),
        len(unique_pages),
        removed_count,
        max_hamming_distance,
    )
    return unique_pages


def _is_duplicate_candidate(left: SelectedPage, right: SelectedPage, max_hamming_distance: int) -> bool:
    evidence = _duplicate_evidence(left, right, max_hamming_distance)

    if evidence["hash_distance"] > max_hamming_distance + 6 and evidence["visual_similarity"] < 0.95:
        return False

    temporal_gap = abs(left.segment_start - right.segment_start)
    text_heavy = evidence["text_heavy"]

    # Strong same-page visual match is enough only when captures are local in time,
    # which avoids collapsing consecutive real pages with similar layouts.
    if (
        temporal_gap <= settings.quality_sequence_duplicate_seconds
        and evidence["visual_similarity"] >= 0.98
        and evidence["layout_similarity"] >= 0.94
        and evidence["profile_similarity"] >= 0.92
    ):
        return True

    if (
        temporal_gap <= settings.quality_sequence_duplicate_seconds
        and evidence["visual_similarity"] >= 0.72
        and evidence["layout_similarity"] >= 0.89
        and evidence["profile_similarity"] >= 0.93
        and evidence["text_structure_similarity"] >= 0.84
        and (_is_weak_duplicate_capture(left) or _is_weak_duplicate_capture(right))
    ):
        return True

    if text_heavy:
        text_similarity = max(evidence["ocr_similarity"], evidence["text_structure_similarity"])
        if (
            evidence["visual_similarity"] >= 0.93
            and evidence["layout_similarity"] >= 0.9
            and evidence["profile_similarity"] >= 0.93
            and text_similarity >= settings.quality_duplicate_text_similarity_threshold
        ):
            return True

        if (
            temporal_gap <= settings.quality_sequence_duplicate_seconds
            and evidence["visual_similarity"] >= 0.9
            and evidence["layout_similarity"] >= 0.9
            and evidence["profile_similarity"] >= 0.93
            and evidence["text_structure_similarity"] >= 0.97
        ):
            return True

        return False

    if (
        temporal_gap <= settings.quality_sequence_duplicate_seconds
        and evidence["visual_similarity"] >= settings.quality_duplicate_low_text_visual_threshold
        and evidence["layout_similarity"] >= 0.92
        and evidence["profile_similarity"] >= 0.9
    ):
        return True

    if (
        temporal_gap > settings.quality_sequence_duplicate_seconds
        and evidence["visual_similarity"] >= settings.quality_duplicate_far_visual_threshold
        and evidence["layout_similarity"] >= 0.95
        and evidence["profile_similarity"] >= 0.94
    ):
        return True

    return False


def _duplicate_evidence(
    left: SelectedPage,
    right: SelectedPage,
    max_hamming_distance: int,
) -> dict[str, float | int | bool]:
    hash_distance = _hamming_distance(
        left.selected_frame.quality.perceptual_hash,
        right.selected_frame.quality.perceptual_hash,
    )
    left_signature = _content_signature(left)
    right_signature = _content_signature(right)
    content_diff = float(np.mean(np.abs(left_signature - right_signature)))
    histogram_similarity = _histogram_similarity(left_signature, right_signature)
    layout_similarity = 1.0 - _layout_diff(left, right)
    profile_similarity = 1.0 - _profile_diff(left, right)
    visual_similarity = max(
        0.0,
        min(
            (histogram_similarity * 0.4)
            + ((1.0 - min(content_diff / max(settings.quality_duplicate_content_diff_threshold * 2.0, 0.001), 1.0)) * 0.35)
            + (layout_similarity * 0.15)
            + (profile_similarity * 0.1),
            1.0,
        ),
    )
    text_structure_similarity = _text_structure_similarity(left, right)
    ocr_similarity = _ocr_text_similarity(left, right)
    text_heavy = min(
        left.selected_frame.quality.text_density,
        right.selected_frame.quality.text_density,
    ) >= settings.quality_duplicate_text_density_threshold
    return {
        "hash_distance": hash_distance,
        "visual_similarity": visual_similarity,
        "layout_similarity": layout_similarity,
        "profile_similarity": profile_similarity,
        "text_structure_similarity": text_structure_similarity,
        "ocr_similarity": ocr_similarity,
        "text_heavy": text_heavy,
    }


def _hamming_distance(left_hash: str, right_hash: str) -> int:
    width = max(len(left_hash), len(right_hash))
    left_value = int(left_hash, 16)
    right_value = int(right_hash, 16)
    return (left_value ^ right_value).bit_count() + abs(len(left_hash) - len(right_hash)) * 4


def _content_signature(page: SelectedPage) -> np.ndarray:
    image = _normalized_duplicate_render(page)
    if image is None:
        return np.zeros((48, 48), dtype=np.float32)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (48, 48), interpolation=cv2.INTER_AREA)
    return cv2.normalize(resized.astype(np.float32), None, 0.0, 1.0, cv2.NORM_MINMAX)


def _layout_signature(page: SelectedPage) -> np.ndarray:
    image = _normalized_duplicate_render(page)
    if image is None:
        return np.zeros((40, 40), dtype=np.float32)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (40, 40), interpolation=cv2.INTER_AREA)
    binary = cv2.adaptiveThreshold(
        resized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        15,
        7,
    )
    return binary.astype(np.float32) / 255.0


def _projection_profile(page: SelectedPage) -> tuple[np.ndarray, np.ndarray]:
    layout = _layout_signature(page)
    return np.mean(layout, axis=1), np.mean(layout, axis=0)


def _histogram_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_hist = cv2.calcHist([np.uint8(left * 255)], [0], None, [32], [0, 256])
    right_hist = cv2.calcHist([np.uint8(right * 255)], [0], None, [32], [0, 256])
    left_hist = cv2.normalize(left_hist, None).flatten()
    right_hist = cv2.normalize(right_hist, None).flatten()
    return float(cv2.compareHist(left_hist, right_hist, cv2.HISTCMP_CORREL))


def _layout_diff(left: SelectedPage, right: SelectedPage) -> float:
    left_layout = _layout_signature(left)
    right_layout = _layout_signature(right)
    return float(np.mean(np.abs(left_layout - right_layout)))


def _profile_diff(left: SelectedPage, right: SelectedPage) -> float:
    left_rows, left_cols = _projection_profile(left)
    right_rows, right_cols = _projection_profile(right)
    row_diff = float(np.mean(np.abs(left_rows - right_rows)))
    col_diff = float(np.mean(np.abs(left_cols - right_cols)))
    return (row_diff + col_diff) / 2.0


def _text_structure_similarity(left: SelectedPage, right: SelectedPage) -> float:
    left_tokens = _text_structure_tokens(left)
    right_tokens = _text_structure_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return overlap / max(union, 1)


def _text_structure_tokens(page: SelectedPage) -> set[str]:
    image = _normalized_duplicate_render(page)
    if image is None:
        return set()

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        11,
    )
    binary = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        np.ones((2, 2), np.uint8),
        iterations=1,
    )
    count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    tokens: set[str] = set()
    height, width = binary.shape[:2]
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        if area < 18 or w < 3 or h < 3:
            continue
        row_bucket = min(int((y / max(height, 1)) * 8), 7)
        col_bucket = min(int((x / max(width, 1)) * 8), 7)
        size_bucket = min(int((area / max(height * width, 1)) * 8000), 9)
        tokens.add(f"r{row_bucket}c{col_bucket}s{size_bucket}")
    return tokens


def _ocr_text_similarity(left: SelectedPage, right: SelectedPage) -> float:
    left_text = _ocr_text(left)
    right_text = _ocr_text(right)
    if not left_text or not right_text:
        return 0.0
    return SequenceMatcher(a=left_text, b=right_text).ratio()


def _ocr_text(page: SelectedPage) -> str:
    if pytesseract is None or shutil.which("tesseract") is None:
        return ""

    image = _normalized_duplicate_render(page)
    if image is None:
        return ""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    try:
        text = pytesseract.image_to_string(normalized, config="--psm 6")
    except Exception:  # pragma: no cover
        return ""
    compact = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return compact


def _page_quality_rank(page: SelectedPage) -> float:
    quality = page.selected_frame.quality
    return (
        quality.score
        + (quality.readability_score * 0.5)
        + (quality.single_page_score * 0.28)
        + (quality.page_coverage * 0.2)
        + (quality.contour_confidence * 0.16)
        + (quality.stability_score * 0.22)
        - (quality.transition_penalty * 0.55)
        - (quality.occlusion_ratio * 0.45)
        - (quality.background_intrusion_ratio * 0.35)
        - (quality.gutter_ratio * 0.3)
        - (quality.opposing_page_ratio * 0.3)
    )


def _is_weak_duplicate_capture(page: SelectedPage) -> bool:
    quality = page.selected_frame.quality
    return (
        quality.rejected
        or quality.page_coverage < 0.68
        or quality.single_page_score < 0.78
        or quality.background_intrusion_ratio > 0.08
        or quality.transition_penalty > 0.14
    )


def _normalized_duplicate_render(page: SelectedPage):
    image = page.selected_frame.image
    if image is None:
        return None

    quality = page.selected_frame.quality
    if (
        quality.contour_confidence < 0.999
        or quality.page_coverage < 0.999
        or quality.single_page_score < 0.999
    ):
        image = normalize_final_page(image)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    standardized = cv2.resize(normalized, (512, 704), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(standardized, cv2.COLOR_GRAY2BGR)
