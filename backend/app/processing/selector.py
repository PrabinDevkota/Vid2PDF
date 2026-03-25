from app.processing.types import SelectedPage, StableSegment


def select_best_frames(segments: list[StableSegment]) -> list[SelectedPage]:
    selected_pages: list[SelectedPage] = []

    for index, segment in enumerate(segments, start=1):
        best_frame = max(segment.candidate_frames, key=lambda frame: frame.sharpness_score)
        selected_pages.append(
            SelectedPage(
                page_id=f"page-{index}",
                page_number=index,
                label=f"Page Preview {index}",
                source_segment_id=segment.segment_id,
                selected_frame=best_frame,
            )
        )

    return selected_pages
