from __future__ import annotations

from app.processing.latex_builder import EMPTY_PAGE_PLACEHOLDER, build_latex_document, escape_latex
from app.processing.ocr import (
    PageText,
    TextBlock,
    find_consecutive_near_duplicates,
    normalize_ocr_text,
    text_similarity,
)
from app.processing.page_fallback import FALLBACK_NOTE, ensure_pages_from_frames
from app.processing.types import FrameQuality, SampledFrame, SelectedPage


def _make_quality(*, score: float = 0.5, rejected: bool = False) -> FrameQuality:
    return FrameQuality(
        sharpness=score,
        brightness=0.5,
        contrast=0.5,
        edge_density=0.1,
        page_coverage=1.0,
        rectangularity=1.0,
        occlusion_ratio=0.0,
        transition_penalty=0.0,
        readability_score=score,
        sharpness_score=score,
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
        rejected=rejected,
        rejection_reasons=["severe_defocus"] if rejected else [],
        score=score,
        perceptual_hash="0",
    )


def test_escape_latex_special_characters() -> None:
    raw = r"Price is $5 & 10% #1 {a_b} ~ ^ \ path"
    escaped = escape_latex(raw)
    assert r"\$" in escaped
    assert r"\&" in escaped
    assert r"\%" in escaped
    assert r"\#" in escaped
    assert r"\_" in escaped
    assert r"\{" in escaped
    assert r"\}" in escaped
    assert r"\textasciitilde{}" in escaped
    assert r"\textasciicircum{}" in escaped
    assert r"\textbackslash{}" in escaped


def test_normalize_ocr_text_hyphenation_and_whitespace() -> None:
    raw = "This is an exam-\nple of  spaced\n\ntext."
    cleaned = normalize_ocr_text(raw)
    assert "example" in cleaned
    assert "  " not in cleaned
    assert "\n\n" in cleaned


def test_text_similarity_identical() -> None:
    assert text_similarity("Hello World", "hello   world") == 1.0


def test_find_consecutive_near_duplicates() -> None:
    pages = [
        PageText(page_id="page-1", page_number=1, raw_text="Alpha beta gamma", status="ready"),
        PageText(page_id="page-2", page_number=2, raw_text="Alpha beta gamma", status="ready"),
        PageText(page_id="page-3", page_number=3, raw_text="Completely different content", status="ready"),
    ]
    flags = find_consecutive_near_duplicates(pages, threshold=0.9)
    assert len(flags) == 1
    assert flags[0][0] == "page-1"
    assert flags[0][1] == "page-2"
    assert flags[0][2] >= 0.9


def test_find_consecutive_near_duplicates_skips_distinct_pages() -> None:
    pages = [
        PageText(page_id="page-1", page_number=1, raw_text="First unique page", status="ready"),
        PageText(page_id="page-2", page_number=2, raw_text="Second unique page with other words", status="ready"),
    ]
    flags = find_consecutive_near_duplicates(pages, threshold=0.92)
    assert flags == []


def test_build_latex_document_preserves_page_count_and_empty_placeholder() -> None:
    pages = [
        PageText(
            page_id="page-1",
            page_number=1,
            blocks=[TextBlock(text="Hello from page one", confidence=90, top=10, left=10)],
            raw_text="Hello from page one",
            status="ready",
        ),
        PageText(
            page_id="page-2",
            page_number=2,
            blocks=[],
            raw_text="",
            status="empty",
        ),
    ]
    latex = build_latex_document(title="Demo Doc", pages=pages, source_filename="demo.mp4")
    assert r"\begin{document}" in latex
    assert r"\section*{Page 1}" in latex
    assert r"\section*{Page 2}" in latex
    assert r"\newpage" in latex
    assert "Hello from page one" in latex
    assert EMPTY_PAGE_PLACEHOLDER in latex
    assert "Demo Doc" in latex
    assert r"\definecolor{VidAccent}{HTML}{0F766E}" in latex
    assert r"\usepackage[dvipsnames,svgnames,table]{xcolor}" in latex
    assert r"\usepackage{titlesec}" in latex
    assert r"\justifying" in latex
    assert r"\usepackage{ragged2e}" in latex
    assert r"\usepackage{microtype}" in latex


def test_gibberish_text_is_rejected() -> None:
    from app.processing.ocr import is_plausible_page_text

    assert is_plausible_page_text("Atomic Habits is a practical guide to building better habits.")
    assert not is_plausible_page_text("oe a we ee ee ee SE SS SS ee ee a = SS a ee")


def test_ocr_fast_accept_score_setting_exists() -> None:
    from app.core.settings import settings

    assert settings.ocr_fast_accept_score > 0
    assert settings.ocr_dedupe_use_tesseract is False
    assert settings.ocr_upscale_min_width <= 1600


def test_collapse_ocr_duplicate_pages_keeps_better_copy() -> None:
    from app.processing.ocr import collapse_ocr_duplicate_pages
    from app.processing.types import FrameQuality, SampledFrame, SelectedPage

    def make_page(page_id: str, score: float) -> SelectedPage:
        quality = FrameQuality(
            sharpness=score,
            brightness=0.5,
            contrast=0.5,
            edge_density=0.1,
            page_coverage=1.0,
            rectangularity=1.0,
            occlusion_ratio=0.0,
            transition_penalty=0.0,
            readability_score=score,
            sharpness_score=score,
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
            score=score,
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
            image_path="",
            thumbnail_path="",
        )

    pages = [make_page("page-a", 0.4), make_page("page-b", 0.9)]
    ocr = [
        PageText(page_id="page-a", page_number=1, raw_text="Atomic Habits title page content here", status="ready"),
        PageText(page_id="page-b", page_number=2, raw_text="Atomic Habits title page content here", status="ready"),
    ]
    kept_pages, kept_ocr, removed = collapse_ocr_duplicate_pages(pages, ocr, threshold=0.85)
    assert removed == 1
    assert len(kept_pages) == 1
    assert kept_pages[0].page_id == "page-b"
    assert kept_ocr[0].page_id == "page-b"


def test_build_latex_document_escapes_body_text() -> None:
    pages = [
        PageText(
            page_id="page-1",
            page_number=1,
            blocks=[TextBlock(text="Cost is $10 & 20%", confidence=88, top=0, left=0)],
            raw_text="Cost is $10 & 20%",
            status="ready",
        )
    ]
    latex = build_latex_document(title="Money", pages=pages)
    assert r"\$10" in latex
    assert r"\&" in latex
    assert r"\%" in latex


def test_build_latex_document_colors_headings() -> None:
    pages = [
        PageText(
            page_id="page-1",
            page_number=1,
            blocks=[
                TextBlock(text="CHAPTER OVERVIEW", confidence=90, top=0, left=0),
                TextBlock(text="This is the body paragraph with details.", confidence=88, top=40, left=0),
            ],
            raw_text="CHAPTER OVERVIEW\n\nThis is the body paragraph with details.",
            status="ready",
        )
    ]
    latex = build_latex_document(title="Styled", pages=pages)
    assert r"\subsection*" in latex
    assert "VidAccent" in latex


def test_ensure_pages_from_frames_fallback_when_empty() -> None:
    frame = SampledFrame(
        timestamp=1.2,
        frame_index=12,
        image=None,
        quality=_make_quality(score=0.33, rejected=True),
    )
    pages, used_fallback = ensure_pages_from_frames(
        unique_pages=[],
        sequence_pages=[],
        selected_pages=[],
        sampled_frames=[frame],
        processing_mode="screen",
    )
    assert used_fallback is True
    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert FALLBACK_NOTE
