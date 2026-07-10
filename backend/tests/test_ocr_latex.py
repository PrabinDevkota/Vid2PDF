from __future__ import annotations

from app.processing.latex_builder import EMPTY_PAGE_PLACEHOLDER, build_latex_document, escape_latex
from app.processing.ocr import (
    PageText,
    TextBlock,
    find_consecutive_near_duplicates,
    normalize_ocr_text,
    text_similarity,
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
