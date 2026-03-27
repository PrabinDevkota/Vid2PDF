from pathlib import Path

import cv2
import numpy as np

from app.processing.preview import attach_previews
from app.processing.scoring import compute_frame_quality
from app.processing.selector import select_best_frames
from app.processing.deduper import remove_duplicates
from app.processing.types import (
    DocumentDetection,
    FrameQuality,
    PipelineContext,
    SampledFrame,
    SelectedPage,
    StableSegment,
)


def _build_page_image(*, blur: bool = False, darken: int = 0, shift_x: int = 0) -> np.ndarray:
    image = np.full((520, 380, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (40 + shift_x, 32), (322 + shift_x, 470), (242, 242, 242), thickness=-1)
    cv2.rectangle(image, (40 + shift_x, 32), (322 + shift_x, 470), (190, 190, 190), thickness=2)
    for row in range(14):
        y = 62 + (row * 26)
        cv2.line(image, (74 + shift_x, y), (288 + shift_x, y), (35 + darken, 35 + darken, 35 + darken), 2)
    if blur:
        image = cv2.GaussianBlur(image, (13, 13), 4.0)
    return image


def _make_detection(
    corrected_image: np.ndarray,
    *,
    page_coverage: float = 0.72,
    rectangularity: float = 0.9,
    occlusion_ratio: float = 0.0,
    perspective_score: float = 0.95,
    single_page_score: float = 0.92,
    background_intrusion_ratio: float = 0.03,
    border_touch_ratio: float = 0.02,
    text_density: float = 0.03,
    normalized: bool = True,
) -> DocumentDetection:
    return DocumentDetection(
        found=True,
        contour=np.array([[[0, 0]], [[1, 0]], [[1, 1]], [[0, 1]]], dtype=np.int32),
        corrected_image=corrected_image,
        page_coverage=page_coverage,
        rectangularity=rectangularity,
        occlusion_ratio=occlusion_ratio,
        perspective_score=perspective_score,
        single_page_score=single_page_score,
        background_intrusion_ratio=background_intrusion_ratio,
        border_touch_ratio=border_touch_ratio,
        text_density=text_density,
        normalized=normalized,
    )


def _make_sampled_frame(
    frame_index: int,
    timestamp: float,
    score: float,
    *,
    rejected: bool = False,
    transition_penalty: float = 0.02,
    single_page_score: float = 0.95,
    page_coverage: float = 0.82,
    background_intrusion_ratio: float = 0.02,
) -> SampledFrame:
    quality = FrameQuality(
        sharpness=2200.0,
        brightness=180.0,
        contrast=66.0,
        edge_density=0.04,
        page_coverage=page_coverage,
        rectangularity=0.92,
        occlusion_ratio=0.0,
        transition_penalty=transition_penalty,
        readability_score=0.88,
        sharpness_score=0.9,
        contrast_score=0.85,
        brightness_score=0.92,
        text_density=0.028,
        single_page_score=single_page_score,
        background_intrusion_ratio=background_intrusion_ratio,
        border_touch_ratio=0.02,
        stability_score=0.95,
        rejected=rejected,
        rejection_reasons=["rejected"] if rejected else [],
        score=score,
        perceptual_hash="0f0f0f0f0f0f0f0f",
    )
    return SampledFrame(
        timestamp=timestamp,
        frame_index=frame_index,
        image=_build_page_image(),
        quality=quality,
        change_ratio=0.02,
    )


def test_blurred_transition_frame_is_rejected() -> None:
    clean_image = _build_page_image()
    blurred_image = _build_page_image(blur=True)
    detection = _make_detection(clean_image)

    clean_quality = compute_frame_quality(clean_image, mode="camera", detection=detection, transition_penalty=0.08)
    blurred_quality = compute_frame_quality(
        blurred_image,
        mode="camera",
        detection=_make_detection(blurred_image),
        transition_penalty=0.56,
    )

    assert clean_quality.rejected is False
    assert blurred_quality.rejected is True
    assert "transition_motion" in blurred_quality.rejection_reasons


def test_near_duplicate_pages_collapse_to_best_candidate() -> None:
    base_image = _build_page_image()
    variant_image = _build_page_image(darken=10, shift_x=4)
    left = SelectedPage(
        page_id="page-a",
        page_number=1,
        label="Page A",
        source_segment_id="segment-a",
        segment_start=1.0,
        segment_end=2.0,
        selected_frame=_make_sampled_frame(10, 1.2, 0.82),
        image_path="",
        thumbnail_path="",
    )
    right = SelectedPage(
        page_id="page-b",
        page_number=2,
        label="Page B",
        source_segment_id="segment-b",
        segment_start=2.2,
        segment_end=3.2,
        selected_frame=_make_sampled_frame(20, 2.4, 0.95),
        image_path="",
        thumbnail_path="",
    )
    left.selected_frame.image = base_image
    right.selected_frame.image = variant_image

    deduped = remove_duplicates([left, right], max_hamming_distance=6)

    assert len(deduped) == 1
    assert deduped[0].source_segment_id == "segment-b"


def test_selector_prefers_clean_single_page_over_partial_spread() -> None:
    partial = _make_sampled_frame(
        5,
        1.0,
        0.9,
        single_page_score=0.28,
        page_coverage=0.48,
        background_intrusion_ratio=0.26,
    )
    clean = _make_sampled_frame(6, 1.5, 0.84, single_page_score=0.96, page_coverage=0.86)
    segment = StableSegment(
        segment_id="segment-1",
        start_time=0.8,
        end_time=2.0,
        candidate_frames=[partial, clean],
        mean_change_ratio=0.03,
    )

    selected = select_best_frames([segment], processing_mode="camera")

    assert len(selected) == 1
    assert selected[0].selected_frame.frame_index == 6


def test_selector_prefers_stable_frame_over_sharper_transition_frame() -> None:
    unstable = _make_sampled_frame(30, 4.0, 0.96, transition_penalty=0.48, rejected=True)
    stable = _make_sampled_frame(31, 4.4, 0.86, transition_penalty=0.05)
    segment = StableSegment(
        segment_id="segment-2",
        start_time=3.8,
        end_time=4.8,
        candidate_frames=[unstable, stable],
        mean_change_ratio=0.04,
    )

    selected = select_best_frames([segment], processing_mode="camera")

    assert len(selected) == 1
    assert selected[0].selected_frame.frame_index == 31


def test_attach_previews_uses_normalized_selected_candidate_consistently(tmp_path: Path) -> None:
    raw_image = _build_page_image()
    context = PipelineContext(
        job_id="job-quality",
        upload_path="video.mp4",
        job_root=str(tmp_path / "job-quality"),
        page_dir=str(tmp_path / "job-quality" / "pages"),
        thumbnail_dir=str(tmp_path / "job-quality" / "thumbnails"),
        artifact_base_url="/artifacts",
        processing_mode="camera",
    )
    page = SelectedPage(
        page_id="page-1",
        page_number=1,
        label="Page 1",
        source_segment_id="segment-1",
        segment_start=0.0,
        segment_end=1.0,
        selected_frame=_make_sampled_frame(1, 0.4, 0.9),
        image_path="",
        thumbnail_path="",
    )
    page.selected_frame.image = raw_image

    attach_previews([page], context=context)
    written = cv2.imread(page.image_path)

    assert written is not None
    assert page.selected_frame.image is not None
    assert written.shape == page.selected_frame.image.shape
    assert np.array_equal(written, page.selected_frame.image)
