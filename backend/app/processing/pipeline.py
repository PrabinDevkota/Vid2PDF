import logging
from dataclasses import dataclass

from app.core.settings import settings
from app.processing.context import build_pipeline_context
from app.processing.deduper import remove_duplicates
from app.processing.debug import write_pipeline_debug_report
from app.processing.exporter import ExportArtifact, export_pdf
from app.processing.ocr import (
    PageText,
    collapse_ocr_duplicate_pages,
    extract_pages_text_parallel,
    find_consecutive_near_duplicates,
)
from app.processing.page_fallback import FALLBACK_NOTE, ensure_pages_from_frames
from app.processing.preview import attach_previews
from app.processing.sampler import load_video_metadata, sample_frames
from app.processing.sequence import collapse_sequence_candidates
from app.processing.segmenter import detect_stable_segments
from app.processing.selector import select_best_frames
from app.processing.tectonic_exporter import TextExportArtifact, compile_latex_with_tectonic
from app.processing.types import PipelineContext, SelectedPage, VideoMetadata

logger = logging.getLogger(__name__)

PIPELINE_STAGES = [
    ("sample_frames", "Sample frames from the uploaded video"),
    ("detect_segments", "Detect stable page-view segments"),
    ("select_frames", "Select the clearest frame per segment"),
    ("remove_duplicates", "Remove duplicate or weak pages"),
    ("prepare_previews", "Prepare preview metadata"),
    ("extract_text", "Extract text from unique page frames"),
]


@dataclass
class PipelineResult:
    notes: list[str]
    pages: list[SelectedPage]
    video_metadata: VideoMetadata
    context: PipelineContext


# How aggressively segmentation splits the video into pages. "more" lowers
# every splitting threshold (more, possibly duplicated pages); "fewer" raises
# them (fewer, safer pages).
SENSITIVITY_FACTORS: dict[str, float] = {"fewer": 1.6, "balanced": 1.0, "more": 0.55}


def mode_settings(processing_mode: str, sensitivity: str = "balanced") -> dict[str, float | int]:
    if processing_mode == "camera":
        base: dict[str, float | int] = {
            "sample_fps": settings.camera_sample_fps,
            "min_seconds": settings.camera_stable_segment_min_seconds,
            "max_change_ratio": settings.camera_stable_segment_max_change_ratio,
            "hash_distance_threshold": settings.camera_stable_segment_hash_distance_threshold,
            "mean_diff_threshold": settings.camera_stable_segment_mean_diff_threshold,
            "dedupe_threshold": settings.camera_dedupe_max_hash_distance,
        }
    else:
        base = {
            "sample_fps": settings.screen_sample_fps,
            "min_seconds": settings.screen_stable_segment_min_seconds,
            "max_change_ratio": settings.screen_stable_segment_max_change_ratio,
            "hash_distance_threshold": settings.screen_stable_segment_hash_distance_threshold,
            "mean_diff_threshold": settings.screen_stable_segment_mean_diff_threshold,
            "dedupe_threshold": settings.screen_dedupe_max_hash_distance,
        }

    factor = SENSITIVITY_FACTORS.get(sensitivity, 1.0)
    base["adaptive_std_scale"] = factor
    base["min_seconds"] = float(base["min_seconds"]) * factor
    base["max_change_ratio"] = float(base["max_change_ratio"]) * factor
    base["mean_diff_threshold"] = float(base["mean_diff_threshold"]) * factor
    if sensitivity == "more":
        base["sample_fps"] = float(base["sample_fps"]) * 1.5
        base["dedupe_threshold"] = max(1, int(base["dedupe_threshold"]) - 1)
    elif sensitivity == "fewer":
        base["dedupe_threshold"] = int(base["dedupe_threshold"]) + 2
    return base


def camera_detection_failed(sampled_frames: list) -> bool:
    if not sampled_frames:
        return True
    return not any(
        frame.detection is not None and frame.detection.found for frame in sampled_frames
    )


def run_reconstruction_pipeline(
    job_id: str,
    upload_path: str,
    processing_mode: str,
    sensitivity: str = "balanced",
    trim_start: float | None = None,
    trim_end: float | None = None,
) -> PipelineResult:
    context = build_pipeline_context(
        job_id=job_id,
        upload_path=upload_path,
        processing_mode=processing_mode,
    )
    mode = mode_settings(context.processing_mode, sensitivity)
    notes: list[str] = []

    metadata = load_video_metadata(upload_path)
    sampled_frames = sample_frames(
        context=context,
        metadata=metadata,
        sample_fps=float(mode["sample_fps"]),
        start_seconds=trim_start,
        end_seconds=trim_end,
    )

    if context.processing_mode == "camera" and camera_detection_failed(sampled_frames):
        notes.append(
            "Camera mode found no page contours; automatically switched to screen mode."
        )
        context = build_pipeline_context(
            job_id=job_id,
            upload_path=upload_path,
            processing_mode="screen",
        )
        mode = mode_settings("screen", sensitivity)
        sampled_frames = sample_frames(
            context=context,
            metadata=metadata,
            sample_fps=float(mode["sample_fps"]),
            start_seconds=trim_start,
            end_seconds=trim_end,
        )

    segments = detect_stable_segments(
        frames=sampled_frames,
        min_seconds=float(mode["min_seconds"]),
        max_change_ratio=float(mode["max_change_ratio"]),
        hash_distance_threshold=int(mode["hash_distance_threshold"]),
        mean_diff_threshold=float(mode["mean_diff_threshold"]),
        adaptive_std_scale=float(mode["adaptive_std_scale"]),
    )
    selected_pages = select_best_frames(
        segments,
        processing_mode=context.processing_mode,
    )
    sequence_pages = collapse_sequence_candidates(selected_pages)
    unique_pages = remove_duplicates(
        sequence_pages,
        max_hamming_distance=int(mode["dedupe_threshold"]),
    )
    unique_pages, used_fallback = ensure_pages_from_frames(
        unique_pages=unique_pages,
        sequence_pages=sequence_pages,
        selected_pages=selected_pages,
        sampled_frames=sampled_frames,
        processing_mode=context.processing_mode,
    )
    if used_fallback:
        notes.append(FALLBACK_NOTE)

    preview_pages = attach_previews(unique_pages, context=context)
    write_pipeline_debug_report(
        context=context,
        sampled_frames=sampled_frames,
        segments=segments,
        selected_pages=selected_pages,
        sequence_pages=sequence_pages,
        deduped_pages=preview_pages,
    )

    logger.info(
        "Pipeline finished for job=%s: sampled_frames=%s, segments=%s, selected_pages=%s, sequence_pages=%s, deduped_pages=%s",
        job_id,
        len(sampled_frames),
        len(segments),
        len(selected_pages),
        len(sequence_pages),
        len(preview_pages),
    )

    notes.extend(
        [
            f"Processing mode: {context.processing_mode}.",
            f"Processed video at {metadata.fps:.2f} fps, {metadata.width}x{metadata.height}, duration {metadata.duration_seconds:.1f}s.",
            f"Sampled {len(sampled_frames)} frames and detected {len(segments)} stable page segments.",
            f"Selected {len(selected_pages)} representative frames, collapsed to {len(sequence_pages)} sequence-stable candidates, removed {max(len(sequence_pages) - len(preview_pages), 0)} duplicates, and kept {len(preview_pages)} pages after deduplication.",
        ]
    )

    return PipelineResult(
        notes=notes,
        pages=preview_pages,
        video_metadata=metadata,
        context=context,
    )


def build_export(
    job_id: str,
    pages: list[SelectedPage],
    output_dir: str,
    title: str | None = None,
    page_size: str = "auto",
    margin: str = "none",
) -> ExportArtifact:
    return export_pdf(
        job_id=job_id,
        pages=pages,
        output_dir=output_dir,
        title=title,
        page_size=page_size,
        margin=margin,
    )


def build_text_export(
    job_id: str,
    pages: list[PageText],
    output_dir: str,
    *,
    title: str,
    source_filename: str | None = None,
) -> TextExportArtifact:
    return compile_latex_with_tectonic(
        job_id=job_id,
        title=title,
        pages=pages,
        output_dir=output_dir,
        source_filename=source_filename,
    )


def ocr_selected_pages(pages: list[SelectedPage], lang: str | None = None) -> list[PageText]:
    """OCR each unique selected page image, in parallel across CPU cores."""
    jobs = [
        (page.image_path, page.page_id, page.page_number)
        for page in pages
    ]
    return extract_pages_text_parallel(jobs, lang=lang)


def ocr_and_collapse_duplicates(
    pages: list[SelectedPage],
    lang: str | None = None,
) -> tuple[list[SelectedPage], list[PageText], list[str]]:
    """OCR pages, then drop near-duplicate OCR pages keeping the sharper copy."""
    ocr_results = ocr_selected_pages(pages, lang=lang)
    collapsed_pages, collapsed_ocr, removed = collapse_ocr_duplicate_pages(pages, ocr_results)
    notes = collect_ocr_duplicate_notes(collapsed_ocr)
    if removed:
        notes.insert(
            0,
            f"Removed {removed} near-duplicate page(s) after OCR text comparison.",
        )
    return collapsed_pages, collapsed_ocr, notes


def collect_ocr_duplicate_notes(pages: list[PageText]) -> list[str]:
    notes: list[str] = []
    for left_id, right_id, score in find_consecutive_near_duplicates(pages):
        notes.append(
            f"Near-duplicate OCR text between {left_id} and {right_id} "
            f"(similarity {score:.0%}). Review before export if both should be kept."
        )
    return notes
