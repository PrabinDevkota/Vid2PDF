import logging

from app.processing.types import SelectedPage

logger = logging.getLogger(__name__)


def remove_duplicates(
    pages: list[SelectedPage],
    max_hamming_distance: int = 6,
) -> list[SelectedPage]:
    unique_pages: list[SelectedPage] = []
    removed_count = 0

    for page in pages:
        page_hash = page.selected_frame.quality.perceptual_hash
        is_duplicate = any(
            _hamming_distance(page_hash, existing.selected_frame.quality.perceptual_hash)
            <= max_hamming_distance
            for existing in unique_pages
        )
        if not is_duplicate:
            unique_pages.append(page)
        else:
            removed_count += 1

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
