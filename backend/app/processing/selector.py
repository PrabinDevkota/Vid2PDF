from app.processing.types import SelectedPage, StableSegment


def select_best_frames(
    segments: list[StableSegment],
) -> list[SelectedPage]:
    selected_pages: list[SelectedPage] = []

    for index, segment in enumerate(segments, start=1):
        best_frame = max(
            segment.candidate_frames,
            key=lambda frame: frame.quality.score,
        )
        selected_pages.append(
            SelectedPage(
                page_id=f"page-{index}",
                page_number=index,
                label=f"Page {index}",
                source_segment_id=segment.segment_id,
                segment_start=segment.start_time,
                segment_end=segment.end_time,
                selected_frame=best_frame,
                image_path="",
                thumbnail_path="",
                notes=[
                    f"Selected from {len(segment.candidate_frames)} candidate frames.",
                    f"Segment stability delta: {segment.mean_change_ratio:.4f}",
                ],
            )
        )

    return selected_pages
