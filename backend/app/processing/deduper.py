from app.processing.types import SelectedPage


def remove_duplicates(
    pages: list[SelectedPage],
    max_hamming_distance: int = 6,
) -> list[SelectedPage]:
    unique_pages: list[SelectedPage] = []

    for page in pages:
        page_hash = page.selected_frame.quality.perceptual_hash
        is_duplicate = any(
            _hamming_distance(page_hash, existing.selected_frame.quality.perceptual_hash)
            <= max_hamming_distance
            for existing in unique_pages
        )
        if not is_duplicate:
            unique_pages.append(page)

    for index, page in enumerate(unique_pages, start=1):
        page.page_number = index
        page.label = f"Page {index}"
        page.page_id = f"page-{index}"

    return unique_pages


def _hamming_distance(left_hash: str, right_hash: str) -> int:
    width = max(len(left_hash), len(right_hash))
    left_value = int(left_hash, 16)
    right_value = int(right_hash, 16)
    return (left_value ^ right_value).bit_count() + abs(len(left_hash) - len(right_hash)) * 4
