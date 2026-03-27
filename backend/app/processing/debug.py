from __future__ import annotations

import json
from pathlib import Path

import cv2

from app.core.settings import settings
from app.processing.types import PipelineContext, SampledFrame, SelectedPage, StableSegment


def write_pipeline_debug_report(
    *,
    context: PipelineContext,
    sampled_frames: list[SampledFrame],
    segments: list[StableSegment],
    selected_pages: list[SelectedPage],
    sequence_pages: list[SelectedPage],
    deduped_pages: list[SelectedPage],
) -> None:
    if not settings.quality_debug_artifacts_enabled:
        return

    debug_dir = Path(context.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)

    rejected_frames = [frame for frame in sampled_frames if frame.quality.rejected]
    report = {
        "job_id": context.job_id,
        "processing_mode": context.processing_mode,
        "counts": {
            "sampled_frames": len(sampled_frames),
            "rejected_frames": len(rejected_frames),
            "segments": len(segments),
            "selected_pages": len(selected_pages),
            "sequence_pages": len(sequence_pages),
            "deduped_pages": len(deduped_pages),
        },
        "rejected_frames": [_frame_summary(frame) for frame in rejected_frames],
        "segments": [
            {
                "segment_id": segment.segment_id,
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "mean_change_ratio": segment.mean_change_ratio,
                "candidate_frame_indices": [frame.frame_index for frame in segment.candidate_frames],
            }
            for segment in segments
        ],
        "selected_pages": [_page_summary(page) for page in selected_pages],
        "sequence_pages": [_page_summary(page) for page in sequence_pages],
        "deduped_pages": [_page_summary(page) for page in deduped_pages],
    }
    Path(context.debug_report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")

    for index, frame in enumerate(rejected_frames[: settings.quality_debug_max_rejected_frames], start=1):
        _write_image(debug_dir / f"rejected-{index:02d}-frame-{frame.frame_index}.jpg", frame.image)

    for index, page in enumerate(deduped_pages[: settings.quality_debug_max_kept_pages], start=1):
        _write_image(debug_dir / f"kept-{index:02d}-{page.page_id}.jpg", page.selected_frame.image)


def _frame_summary(frame: SampledFrame) -> dict[str, object]:
    quality = frame.quality
    return {
        "frame_index": frame.frame_index,
        "timestamp": frame.timestamp,
        "score": quality.score,
        "readability_score": quality.readability_score,
        "transition_penalty": quality.transition_penalty,
        "single_page_score": quality.single_page_score,
        "page_coverage": quality.page_coverage,
        "background_intrusion_ratio": quality.background_intrusion_ratio,
        "gutter_ratio": quality.gutter_ratio,
        "opposing_page_ratio": quality.opposing_page_ratio,
        "rejection_reasons": quality.rejection_reasons,
    }


def _page_summary(page: SelectedPage) -> dict[str, object]:
    quality = page.selected_frame.quality
    return {
        "page_id": page.page_id,
        "label": page.label,
        "source_segment_id": page.source_segment_id,
        "segment_start": page.segment_start,
        "segment_end": page.segment_end,
        "frame_index": page.selected_frame.frame_index,
        "timestamp": page.selected_frame.timestamp,
        "score": quality.score,
        "readability_score": quality.readability_score,
        "single_page_score": quality.single_page_score,
        "page_coverage": quality.page_coverage,
        "background_intrusion_ratio": quality.background_intrusion_ratio,
        "transition_penalty": quality.transition_penalty,
        "rejected": quality.rejected,
        "rejection_reasons": quality.rejection_reasons,
        "notes": page.notes,
    }


def _write_image(path: Path, image) -> None:
    if image is None:
        return
    cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
