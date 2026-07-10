import logging
from dataclasses import dataclass

from app.core.settings import settings
from app.processing.context import build_pipeline_context
from app.processing.deduper import remove_duplicates
from app.processing.debug import write_pipeline_debug_report
from app.processing.exporter import ExportArtifact, export_pdf
from app.processing.ocr import PageText, extract_page_text, find_consecutive_near_duplicates
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


def run_reconstruction_pipeline(
    job_id: str,
    upload_path: str,
    processing_mode: str,
) -> PipelineResult:
    context = build_pipeline_context(
        job_id=job_id,
        upload_path=upload_path,
        processing_mode=processing_mode,
    )
    if context.processing_mode == "camera":
        sample_fps = settings.camera_sample_fps
        min_seconds = settings.camera_stable_segment_min_seconds
        max_change_ratio = settings.camera_stable_segment_max_change_ratio
        hash_distance_threshold = settings.camera_stable_segment_hash_distance_threshold
        mean_diff_threshold = settings.camera_stable_segment_mean_diff_threshold
        dedupe_threshold = settings.camera_dedupe_max_hash_distance
    else:
        sample_fps = settings.screen_sample_fps
        min_seconds = settings.screen_stable_segment_min_seconds
        max_change_ratio = settings.screen_stable_segment_max_change_ratio
        hash_distance_threshold = settings.screen_stable_segment_hash_distance_threshold
        mean_diff_threshold = settings.screen_stable_segment_mean_diff_threshold
        dedupe_threshold = settings.screen_dedupe_max_hash_distance

    metadata = load_video_metadata(upload_path)
    sampled_frames = sample_frames(
        context=context,
        metadata=metadata,
        sample_fps=sample_fps,
    )
    segments = detect_stable_segments(
        frames=sampled_frames,
        min_seconds=min_seconds,
        max_change_ratio=max_change_ratio,
        hash_distance_threshold=hash_distance_threshold,
        mean_diff_threshold=mean_diff_threshold,
    )
    selected_pages = select_best_frames(
        segments,
        processing_mode=context.processing_mode,
    )
    sequence_pages = collapse_sequence_candidates(selected_pages)
    unique_pages = remove_duplicates(
        sequence_pages,
        max_hamming_distance=dedupe_threshold,
    )
    if not unique_pages and sequence_pages:
        unique_pages = [sequence_pages[0]]
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
        "Pipeline finished for job=%s: sampled_frames=%s, segments=%s, selected_pages=%s, deduped_pages=%s",
        job_id,
        len(sampled_frames),
        len(segments),
        len(selected_pages),
        len(sequence_pages),
        len(preview_pages),
    )

    notes = [
        f"Processing mode: {context.processing_mode}.",
        f"Processed video at {metadata.fps:.2f} fps, {metadata.width}x{metadata.height}, duration {metadata.duration_seconds:.1f}s.",
        f"Sampled {len(sampled_frames)} frames and detected {len(segments)} stable page segments.",
        f"Selected {len(selected_pages)} representative frames, collapsed to {len(sequence_pages)} sequence-stable candidates, removed {len(sequence_pages) - len(preview_pages)} duplicates, and kept {len(preview_pages)} pages after deduplication.",
    ]

    return PipelineResult(
        notes=notes,
        pages=preview_pages,
        video_metadata=metadata,
        context=context,
    )


def build_export(job_id: str, pages: list[SelectedPage], output_dir: str) -> ExportArtifact:
    return export_pdf(job_id=job_id, pages=pages, output_dir=output_dir)


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


def ocr_selected_pages(pages: list[SelectedPage]) -> list[PageText]:
    """OCR each unique selected page image in order."""
    results: list[PageText] = []
    for page in pages:
        results.append(
            extract_page_text(
                page.image_path,
                page_id=page.page_id,
                page_number=page.page_number,
            )
        )
    return results


def collect_ocr_duplicate_notes(pages: list[PageText]) -> list[str]:
    notes: list[str] = []
    for left_id, right_id, score in find_consecutive_near_duplicates(pages):
        notes.append(
            f"Near-duplicate OCR text between {left_id} and {right_id} "
            f"(similarity {score:.0%}). Both pages were kept; review before export."
        )
    return notes
