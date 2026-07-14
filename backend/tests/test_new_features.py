from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.processing.editor import _apply_filter
from app.processing.downloader import is_valid_video_url
from app.processing.ocr import is_plausible_page_text, sanitize_language
from app.processing.pipeline import mode_settings
from app.processing.types import FrameQuality, SampledFrame, SelectedPage


def test_sanitize_language() -> None:
    assert sanitize_language("eng") == "eng"
    assert sanitize_language("nep") == "nep"
    assert sanitize_language("eng+nep") == "eng+nep"
    assert sanitize_language("chi_sim") == "chi_sim"
    # Injection / malformed inputs fall back to the default.
    assert sanitize_language("eng --oem 0") == "eng"
    assert sanitize_language("../evil") == "eng"
    assert sanitize_language("") == "eng"
    assert sanitize_language(None) == "eng"


def test_non_latin_text_bypasses_latin_heuristics() -> None:
    # Devanagari has no ASCII vowels; it must not be rejected as gibberish.
    nepali = "नेपाल एक सुन्दर देश हो र यहाँ धेरै हिमालहरू छन्"
    assert is_plausible_page_text(nepali)


def test_mode_settings_sensitivity_scaling() -> None:
    balanced = mode_settings("screen", "balanced")
    more = mode_settings("screen", "more")
    fewer = mode_settings("screen", "fewer")

    assert more["adaptive_std_scale"] < balanced["adaptive_std_scale"] < fewer["adaptive_std_scale"]
    assert more["min_seconds"] < balanced["min_seconds"] < fewer["min_seconds"]
    assert more["sample_fps"] > balanced["sample_fps"]
    assert fewer["dedupe_threshold"] > balanced["dedupe_threshold"]
    # Unknown values fall back to balanced.
    assert mode_settings("screen", "bogus") == balanced


def test_is_valid_video_url() -> None:
    assert is_valid_video_url("https://www.youtube.com/watch?v=abc123")
    assert is_valid_video_url("http://example.com/video.mp4")
    assert not is_valid_video_url("ftp://example.com/video.mp4")
    assert not is_valid_video_url("file:///C:/secret.mp4")
    assert not is_valid_video_url("not a url")


def test_apply_filter_variants() -> None:
    image = np.full((80, 60, 3), 128, dtype=np.uint8)
    for name in ("none", "grayscale", "bw", "enhance"):
        result = _apply_filter(image, name)
        assert result.shape == image.shape

    grayscale = _apply_filter(image, "grayscale")
    assert (grayscale[:, :, 0] == grayscale[:, :, 1]).all()
    bw = _apply_filter(image, "bw")
    assert set(np.unique(bw)).issubset({0, 255})


def _make_page(page_id: str, image_path: str) -> SelectedPage:
    quality = FrameQuality(
        sharpness=0.5,
        brightness=0.5,
        contrast=0.5,
        edge_density=0.1,
        page_coverage=1.0,
        rectangularity=1.0,
        occlusion_ratio=0.0,
        transition_penalty=0.0,
        readability_score=0.5,
        sharpness_score=0.5,
        contrast_score=0.5,
        brightness_score=0.5,
        text_density=0.02,
        single_page_score=1.0,
        background_intrusion_ratio=0.0,
        border_touch_ratio=0.0,
        contour_confidence=1.0,
        gutter_ratio=0.0,
        opposing_page_ratio=0.0,
        stability_score=1.0,
        rejected=False,
        rejection_reasons=[],
        score=0.5,
        perceptual_hash="0",
    )
    frame = SampledFrame(timestamp=1.0, frame_index=1, image=None, quality=quality)
    return SelectedPage(
        page_id=page_id,
        page_number=1,
        label="Page",
        source_segment_id=page_id,
        segment_start=1.0,
        segment_end=2.0,
        selected_frame=frame,
        image_path=image_path,
        thumbnail_path="",
    )


def test_export_searchable_pdf(tmp_path: Path) -> None:
    pytest.importorskip("pypdf")
    from app.processing.ocr import resolve_tesseract_cmd
    from app.processing.searchable_exporter import export_searchable_pdf

    try:
        resolve_tesseract_cmd()
    except RuntimeError:
        pytest.skip("Tesseract not installed")

    image_paths = []
    for index, word in enumerate(("HELLO WORLD", "SECOND PAGE")):
        image = Image.new("RGB", (600, 400), "white")
        draw = ImageDraw.Draw(image)
        draw.text((40, 180), word, fill="black")
        path = tmp_path / f"page-{index + 1}.png"
        image.save(path)
        image_paths.append(str(path))

    pages = [_make_page(f"page-{i + 1}", p) for i, p in enumerate(image_paths)]
    artifact = export_searchable_pdf(
        "testjob",
        pages,
        str(tmp_path),
        title="Test Doc",
        lang="eng",
    )
    assert artifact.page_count == 2

    from pypdf import PdfReader

    pdf_path = tmp_path / artifact.filename
    reader = PdfReader(str(pdf_path))
    assert len(reader.pages) == 2
    assert reader.metadata is not None and reader.metadata.title == "Test Doc"
    # The invisible text layer should be extractable.
    combined = " ".join(page.extract_text() or "" for page in reader.pages)
    assert "HELLO" in combined.upper()
