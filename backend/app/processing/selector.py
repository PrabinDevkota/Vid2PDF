from app.processing.types import ProcessingMode, SelectedPage, StableSegment


def select_best_frames(
    segments: list[StableSegment],
    processing_mode: ProcessingMode,
) -> list[SelectedPage]:
    selected_pages: list[SelectedPage] = []

    for index, segment in enumerate(segments, start=1):
        best_frame = max(segment.candidate_frames, key=lambda frame: _frame_selection_score(frame, segment, processing_mode))
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


def _frame_selection_score(frame, segment: StableSegment, processing_mode: ProcessingMode) -> float:
    base_score = frame.quality.score
    if processing_mode != "camera":
        return base_score

    segment_midpoint = (segment.start_time + segment.end_time) / 2.0
    segment_duration = max(segment.end_time - segment.start_time, 0.001)
    distance_from_middle = abs(frame.timestamp - segment_midpoint) / segment_duration
    middle_bonus = max(0.0, 1.0 - (distance_from_middle * 2.0)) * 0.18
    stability_bonus = max(0.0, 1.0 - frame.change_ratio) * 0.15
    coverage_bonus = frame.quality.page_coverage * 0.16
    rectangularity_bonus = frame.quality.rectangularity * 0.12
    occlusion_penalty = frame.quality.occlusion_ratio * 0.35
    transition_penalty = frame.quality.transition_penalty * 0.45
    return (
        base_score
        + middle_bonus
        + stability_bonus
        + coverage_bonus
        + rectangularity_bonus
        - occlusion_penalty
        - transition_penalty
    )
