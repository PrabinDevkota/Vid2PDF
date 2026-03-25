from dataclasses import dataclass

from app.core.settings import settings
from app.processing.deduper import remove_duplicates
from app.processing.exporter import ExportArtifact, export_pdf
from app.processing.preview import attach_previews
from app.processing.sampler import sample_frames
from app.processing.segmenter import detect_stable_segments
from app.processing.selector import select_best_frames
from app.processing.types import SelectedPage

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


def run_reconstruction_pipeline(filename: str) -> PipelineResult:
    sampled_frames = sample_frames(filename=filename, fps=settings.default_sample_fps)
    segments = detect_stable_segments(
        frames=sampled_frames,
        min_seconds=settings.stable_segment_min_seconds,
    )
    selected_pages = select_best_frames(segments)
    unique_pages = remove_duplicates(selected_pages)
    preview_pages = attach_previews(unique_pages)

    notes = [
        "Pipeline executed in scaffold mode with deterministic placeholder data.",
        "Real video decoding, scoring, and export logic can slot into the existing stage boundaries.",
    ]

    return PipelineResult(notes=notes, pages=preview_pages)


def build_export(job_id: str, pages: list[SelectedPage]) -> ExportArtifact:
    return export_pdf(job_id=job_id, pages=pages)
