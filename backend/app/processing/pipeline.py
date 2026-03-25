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


def run_reconstruction_pipeline(job_id: str, upload_path: str) -> PipelineResult:
    context = build_pipeline_context(job_id=job_id, upload_path=upload_path)
    metadata = load_video_metadata(upload_path)
    sampled_frames = sample_frames(
        context=context,
        metadata=metadata,
        sample_fps=settings.default_sample_fps,
    )
    segments = detect_stable_segments(
        frames=sampled_frames,
        min_seconds=settings.stable_segment_min_seconds,
        max_change_ratio=settings.stable_segment_max_change_ratio,
    )
    selected_pages = select_best_frames(segments)
    unique_pages = remove_duplicates(selected_pages)
    if not unique_pages and selected_pages:
        unique_pages = [selected_pages[0]]
    preview_pages = attach_previews(unique_pages, context=context)

    notes = [
        f"Processed video at {metadata.fps:.2f} fps, {metadata.width}x{metadata.height}, duration {metadata.duration_seconds:.1f}s.",
        f"Sampled {len(sampled_frames)} frames and detected {len(segments)} stable page segments.",
        f"Selected {len(selected_pages)} representative frames and kept {len(preview_pages)} pages after deduplication.",
    ]

    return PipelineResult(
        notes=notes,
        pages=preview_pages,
        video_metadata=metadata,
        context=context,
    )


def build_export(job_id: str, pages: list[SelectedPage], output_dir: str) -> ExportArtifact:
    return export_pdf(job_id=job_id, pages=pages, output_dir=output_dir)
