from app.processing.types import ProcessingMode, SelectedPage, StableSegment


def select_best_frames(
    segments: list[StableSegment],
    processing_mode: ProcessingMode,
) -> list[SelectedPage]:
    selected_pages: list[SelectedPage] = []

    for index, segment in enumerate(segments, start=1):
        accepted_frames = [frame for frame in segment.candidate_frames if not frame.quality.rejected]
        candidate_pool = accepted_frames if accepted_frames else segment.candidate_frames
        if not candidate_pool:
            continue

        best_frame = max(
            candidate_pool,
            key=lambda frame: _frame_selection_score(frame, segment, processing_mode),
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


def _frame_selection_score(frame, segment: StableSegment, processing_mode: ProcessingMode) -> float:
    base_score = frame.quality.score
    segment_midpoint = (segment.start_time + segment.end_time) / 2.0
    segment_duration = max(segment.end_time - segment.start_time, 0.001)
    distance_from_middle = abs(frame.timestamp - segment_midpoint) / segment_duration
    middle_bonus = max(0.0, 1.0 - (distance_from_middle * 2.0)) * 0.12
    stability_bonus = max(0.0, 1.0 - frame.change_ratio) * 0.16
    readability_bonus = frame.quality.readability_score * 0.18
    text_bonus = min(frame.quality.text_density * 10.0, 0.18)
    rejection_penalty = 0.65 if frame.quality.rejected else 0.0

    score = base_score + middle_bonus + stability_bonus + readability_bonus + text_bonus - rejection_penalty
    if processing_mode != "camera":
        return score

    score += (
        (frame.quality.page_coverage * 0.14)
        + (frame.quality.rectangularity * 0.08)
        + (frame.quality.single_page_score * 0.2)
        + (frame.quality.stability_score * 0.18)
        - (frame.quality.occlusion_ratio * 0.42)
        - (frame.quality.background_intrusion_ratio * 0.44)
        - (frame.quality.border_touch_ratio * 0.25)
        - (frame.quality.transition_penalty * 0.55)
    )
    return score
