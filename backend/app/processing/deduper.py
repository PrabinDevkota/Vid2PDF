import logging

import cv2
import numpy as np

from app.core.settings import settings
from app.processing.types import SelectedPage

logger = logging.getLogger(__name__)


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
                if _is_near_duplicate(page, existing, max_hamming_distance)
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


def _hamming_distance(left_hash: str, right_hash: str) -> int:
    width = max(len(left_hash), len(right_hash))
    left_value = int(left_hash, 16)
    right_value = int(right_hash, 16)
    return (left_value ^ right_value).bit_count() + abs(len(left_hash) - len(right_hash)) * 4


def _is_near_duplicate(left: SelectedPage, right: SelectedPage, max_hamming_distance: int) -> bool:
    hash_distance = _hamming_distance(
        left.selected_frame.quality.perceptual_hash,
        right.selected_frame.quality.perceptual_hash,
    )
    if hash_distance > max_hamming_distance + 6:
        return False

    left_signature = _content_signature(left)
    right_signature = _content_signature(right)
    content_diff = float(np.mean(np.abs(left_signature - right_signature)))
    histogram_similarity = _histogram_similarity(left_signature, right_signature)
    temporal_gap = abs(left.segment_start - right.segment_start)

    if content_diff <= settings.quality_duplicate_content_diff_threshold:
        return True

    if (
        temporal_gap <= settings.quality_sequence_duplicate_seconds
        and hash_distance <= max_hamming_distance + 2
        and histogram_similarity >= settings.quality_duplicate_histogram_threshold
    ):
        return True

    return False


def _content_signature(page: SelectedPage) -> np.ndarray:
    image = page.selected_frame.image
    if image is None:
        return np.zeros((48, 48), dtype=np.float32)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (48, 48), interpolation=cv2.INTER_AREA)
    normalized = cv2.normalize(resized.astype(np.float32), None, 0.0, 1.0, cv2.NORM_MINMAX)
    return normalized


def _histogram_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_hist = cv2.calcHist([np.uint8(left * 255)], [0], None, [32], [0, 256])
    right_hist = cv2.calcHist([np.uint8(right * 255)], [0], None, [32], [0, 256])
    left_hist = cv2.normalize(left_hist, None).flatten()
    right_hist = cv2.normalize(right_hist, None).flatten()
    return float(cv2.compareHist(left_hist, right_hist, cv2.HISTCMP_CORREL))


def _page_quality_rank(page: SelectedPage) -> float:
    quality = page.selected_frame.quality
    return (
        quality.score
        + (quality.readability_score * 0.4)
        + (quality.single_page_score * 0.25)
        + (quality.stability_score * 0.2)
        - (quality.transition_penalty * 0.5)
        - (quality.background_intrusion_ratio * 0.3)
    )
