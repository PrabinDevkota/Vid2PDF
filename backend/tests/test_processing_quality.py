from pathlib import Path

import cv2
import numpy as np

from app.processing.preview import attach_previews
from app.processing.document import detect_document_region
from app.processing.debug import write_pipeline_debug_report
from app.processing.scoring import compute_frame_quality
from app.processing.deduper import remove_duplicates
from app.processing.selector import select_best_frames
from app.processing.sequence import collapse_sequence_candidates
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


def _build_alt_page_image(*, shift_x: int = 0) -> np.ndarray:
    image = np.full((520, 380, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (42 + shift_x, 34), (320 + shift_x, 468), (242, 242, 242), thickness=-1)
    cv2.rectangle(image, (42 + shift_x, 34), (320 + shift_x, 468), (190, 190, 190), thickness=2)
    for row in range(7):
        y = 72 + (row * 48)
        cv2.rectangle(image, (78 + shift_x, y), (272 + shift_x, y + 10), (35, 35, 35), thickness=-1)
    cv2.rectangle(image, (82 + shift_x, 392), (236 + shift_x, 420), (35, 35, 35), thickness=-1)
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
    contour_confidence: float = 0.93,
    gutter_ratio: float = 0.01,
    opposing_page_ratio: float = 0.03,
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
        contour_confidence=contour_confidence,
        gutter_ratio=gutter_ratio,
        opposing_page_ratio=opposing_page_ratio,
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
        contour_confidence=0.94,
        gutter_ratio=0.01,
        opposing_page_ratio=0.03,
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


def test_spread_heavy_detection_is_not_normalized_as_single_page() -> None:
    image = np.full((540, 760, 3), 244, dtype=np.uint8)
    cv2.rectangle(image, (40, 34), (355, 500), (250, 250, 250), thickness=-1)
    cv2.rectangle(image, (405, 34), (720, 500), (250, 250, 250), thickness=-1)
    cv2.rectangle(image, (367, 34), (393, 500), (40, 40, 40), thickness=-1)
    for row in range(15):
        y = 65 + (row * 26)
        cv2.line(image, (72, y), (318, y), (45, 45, 45), 2)
        cv2.line(image, (438, y), (682, y), (45, 45, 45), 2)

    detection = detect_document_region(image)

    assert detection.gutter_ratio > 0.11
    assert detection.single_page_score < 0.58
    assert detection.normalized is False


def test_cluttered_page_detection_is_rejected_by_quality_gate() -> None:
    image = _build_page_image()
    cv2.rectangle(image, (0, 0), (90, 520), (70, 70, 70), thickness=-1)
    cv2.circle(image, (320, 420), 48, (120, 170, 220), thickness=-1)

    detection = _make_detection(
        image,
        background_intrusion_ratio=0.28,
        contour_confidence=0.54,
        opposing_page_ratio=0.24,
        normalized=False,
    )
    quality = compute_frame_quality(image, mode="camera", detection=detection, transition_penalty=0.08)

    assert quality.rejected is True
    assert "background_clutter" in quality.rejection_reasons
    assert "weak_page_isolation" in quality.rejection_reasons


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


def test_deduper_keeps_distinct_page_layouts() -> None:
    first = SelectedPage(
        page_id="page-a",
        page_number=1,
        label="Page A",
        source_segment_id="segment-a",
        segment_start=1.0,
        segment_end=2.0,
        selected_frame=_make_sampled_frame(10, 1.2, 0.9),
        image_path="",
        thumbnail_path="",
    )
    second = SelectedPage(
        page_id="page-b",
        page_number=2,
        label="Page B",
        source_segment_id="segment-b",
        segment_start=2.1,
        segment_end=3.0,
        selected_frame=_make_sampled_frame(20, 2.4, 0.88),
        image_path="",
        thumbnail_path="",
    )
    first.selected_frame.image = _build_page_image()
    second.selected_frame.image = _build_alt_page_image()

    deduped = remove_duplicates([first, second], max_hamming_distance=6)

    assert len(deduped) == 2


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
        debug_dir=str(tmp_path / "job-quality" / "debug"),
        debug_report_path=str(tmp_path / "job-quality" / "debug" / "pipeline_report.json"),
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


def test_pipeline_debug_report_writes_json_and_images(tmp_path: Path) -> None:
    context = PipelineContext(
        job_id="job-debug",
        upload_path="video.mp4",
        job_root=str(tmp_path / "job-debug"),
        page_dir=str(tmp_path / "job-debug" / "pages"),
        thumbnail_dir=str(tmp_path / "job-debug" / "thumbnails"),
        debug_dir=str(tmp_path / "job-debug" / "debug"),
        debug_report_path=str(tmp_path / "job-debug" / "debug" / "pipeline_report.json"),
        artifact_base_url="/artifacts",
        processing_mode="camera",
    )
    rejected = _make_sampled_frame(3, 0.8, 0.3, rejected=True, transition_penalty=0.4)
    kept_page = SelectedPage(
        page_id="page-1",
        page_number=1,
        label="Page 1",
        source_segment_id="segment-1",
        segment_start=0.0,
        segment_end=1.0,
        selected_frame=_make_sampled_frame(4, 1.0, 0.92),
        image_path="",
        thumbnail_path="",
    )

    write_pipeline_debug_report(
        context=context,
        sampled_frames=[rejected, kept_page.selected_frame],
        segments=[],
        selected_pages=[kept_page],
        sequence_pages=[kept_page],
        deduped_pages=[kept_page],
    )

    report_path = Path(context.debug_report_path)
    debug_dir = Path(context.debug_dir)

    assert report_path.exists()
    assert "rejected_frames" in report_path.read_text(encoding="utf-8")
    assert any(path.name.startswith("rejected-") for path in debug_dir.iterdir())
    assert any(path.name.startswith("kept-") for path in debug_dir.iterdir())


def test_sequence_filter_collapses_repeated_turn_moment_captures() -> None:
    first = SelectedPage(
        page_id="page-1",
        page_number=1,
        label="Page 1",
        source_segment_id="segment-a",
        segment_start=1.0,
        segment_end=1.4,
        selected_frame=_make_sampled_frame(10, 1.2, 0.78, transition_penalty=0.16),
        image_path="",
        thumbnail_path="",
    )
    second = SelectedPage(
        page_id="page-2",
        page_number=2,
        label="Page 2",
        source_segment_id="segment-b",
        segment_start=1.5,
        segment_end=1.9,
        selected_frame=_make_sampled_frame(11, 1.7, 0.94, transition_penalty=0.03),
        image_path="",
        thumbnail_path="",
    )
    third = SelectedPage(
        page_id="page-3",
        page_number=3,
        label="Page 3",
        source_segment_id="segment-c",
        segment_start=1.95,
        segment_end=2.25,
        selected_frame=_make_sampled_frame(12, 2.1, 0.81, transition_penalty=0.17),
        image_path="",
        thumbnail_path="",
    )
    base_image = _build_page_image()
    first.selected_frame.image = base_image
    second.selected_frame.image = _build_page_image(darken=4)
    third.selected_frame.image = _build_page_image(shift_x=2)

    collapsed = collapse_sequence_candidates([first, second, third])

    assert len(collapsed) == 1
    assert collapsed[0].source_segment_id == "segment-b"


def test_sequence_filter_prefers_good_center_over_bad_good_bad_neighbors() -> None:
    left_bad = SelectedPage(
        page_id="page-1",
        page_number=1,
        label="Page 1",
        source_segment_id="segment-left",
        segment_start=3.0,
        segment_end=3.4,
        selected_frame=_make_sampled_frame(
            21,
            3.2,
            0.7,
            rejected=True,
            transition_penalty=0.35,
            single_page_score=0.58,
            page_coverage=0.55,
            background_intrusion_ratio=0.14,
        ),
        image_path="",
        thumbnail_path="",
    )
    center_good = SelectedPage(
        page_id="page-2",
        page_number=2,
        label="Page 2",
        source_segment_id="segment-center",
        segment_start=3.45,
        segment_end=3.9,
        selected_frame=_make_sampled_frame(22, 3.65, 0.93, transition_penalty=0.02),
        image_path="",
        thumbnail_path="",
    )
    right_bad = SelectedPage(
        page_id="page-3",
        page_number=3,
        label="Page 3",
        source_segment_id="segment-right",
        segment_start=4.0,
        segment_end=4.3,
        selected_frame=_make_sampled_frame(
            23,
            4.1,
            0.72,
            rejected=True,
            transition_penalty=0.32,
            single_page_score=0.62,
            page_coverage=0.58,
            background_intrusion_ratio=0.12,
        ),
        image_path="",
        thumbnail_path="",
    )

    shared_image = _build_page_image()
    left_bad.selected_frame.image = shared_image
    center_good.selected_frame.image = _build_page_image(darken=3)
    right_bad.selected_frame.image = _build_page_image(shift_x=3)

    collapsed = collapse_sequence_candidates([left_bad, center_good, right_bad])

    assert len(collapsed) == 1
    assert collapsed[0].source_segment_id == "segment-center"
