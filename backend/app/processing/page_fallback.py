from __future__ import annotations

from app.processing.types import ProcessingMode, SampledFrame, SelectedPage, StableSegment
from app.processing.selector import select_best_frames


FALLBACK_NOTE = (
    "All frames failed quality gates; kept best-effort pages. "
    "Prefer Screen mode and pause briefly on each page."
)


def ensure_pages_from_frames(
    *,
    unique_pages: list[SelectedPage],
    sequence_pages: list[SelectedPage],
    selected_pages: list[SelectedPage],
    sampled_frames: list[SampledFrame],
    processing_mode: str,
) -> tuple[list[SelectedPage], bool]:
    """Guarantee at least one page when any frames were sampled.

    Returns (pages, used_fallback).
    """
    if unique_pages:
        return unique_pages, False

    if sequence_pages:
        return [sequence_pages[0]], True

    if selected_pages:
        return [selected_pages[0]], True

    if not sampled_frames:
        return [], False

    best_frame = max(sampled_frames, key=lambda frame: frame.quality.score)
    synthetic_segment = StableSegment(
        segment_id="segment-fallback-1",
        start_time=best_frame.timestamp,
        end_time=best_frame.timestamp,
        candidate_frames=[best_frame],
        mean_change_ratio=best_frame.change_ratio,
    )
    mode: ProcessingMode = "camera" if processing_mode == "camera" else "screen"
    pages = select_best_frames([synthetic_segment], processing_mode=mode)
    if not pages:
        pages = [
            SelectedPage(
                page_id="page-1",
                page_number=1,
                label="Page 1",
                source_segment_id="segment-fallback-1",
                segment_start=best_frame.timestamp,
                segment_end=best_frame.timestamp,
                selected_frame=best_frame,
                image_path="",
                thumbnail_path="",
                notes=["Best-effort fallback page from highest-scoring sampled frame."],
            )
        ]
    else:
        pages[0].notes.append("Best-effort fallback page from highest-scoring sampled frame.")
    return pages, True
