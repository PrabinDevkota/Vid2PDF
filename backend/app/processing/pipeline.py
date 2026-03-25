import logging
from dataclasses import dataclass

from app.core.settings import settings
from app.processing.context import build_pipeline_context
from app.processing.deduper import remove_duplicates
from app.processing.exporter import ExportArtifact, export_pdf
from app.processing.preview import attach_previews
from app.processing.sampler import load_video_metadata, sample_frames
from app.processing.segmenter import detect_stable_segments
from app.processing.selector import select_best_frames
from app.processing.types import PipelineContext, SelectedPage, VideoMetadata

logger = logging.getLogger(__name__)

PIPELINE_STAGES = [
    ("sample_frames", "Sample frames from the uploaded video"),
    ("detect_segments", "Detect stable page-view segments"),
    ("select_frames", "Select the clearest frame per segment"),
    ("remove_duplicates", "Remove duplicate or weak pages"),
    ("prepare_previews", "Prepare preview metadata"),
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
    unique_pages = remove_duplicates(
        selected_pages,
        max_hamming_distance=dedupe_threshold,
    )
    if not unique_pages and selected_pages:
        unique_pages = [selected_pages[0]]
    preview_pages = attach_previews(unique_pages, context=context)

    logger.info(
        "Pipeline finished for job=%s: sampled_frames=%s, segments=%s, selected_pages=%s, deduped_pages=%s",
        job_id,
        len(sampled_frames),
        len(segments),
        len(selected_pages),
        len(preview_pages),
    )

    notes = [
        f"Processing mode: {context.processing_mode}.",
        f"Processed video at {metadata.fps:.2f} fps, {metadata.width}x{metadata.height}, duration {metadata.duration_seconds:.1f}s.",
        f"Sampled {len(sampled_frames)} frames and detected {len(segments)} stable page segments.",
        f"Selected {len(selected_pages)} representative frames, removed {len(selected_pages) - len(preview_pages)} duplicates, and kept {len(preview_pages)} pages after deduplication.",
    ]

    return PipelineResult(
        notes=notes,
        pages=preview_pages,
        video_metadata=metadata,
        context=context,
    )


def build_export(job_id: str, pages: list[SelectedPage], output_dir: str) -> ExportArtifact:
    return export_pdf(job_id=job_id, pages=pages, output_dir=output_dir)
