from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app.processing.ocr import PageText, clean_gibberish_text, is_plausible_page_text

EMPTY_PAGE_PLACEHOLDER = "[No text detected on this page]"
ACCENT = "DocAccent"
INK = "DocInk"
MUTED = "DocMuted"
RULE = "DocRule"


def escape_latex(text: str) -> str:
    """Escape LaTeX special characters in plain text."""
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "#": r"\#",
        "$": r"\$",
        "%": r"\%",
        "&": r"\&",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    pattern = re.compile("|".join(re.escape(key) for key in replacements))
    return pattern.sub(lambda match: replacements[match.group(0)], text)


def build_latex_document(
    *,
    title: str,
    pages: list[PageText],
    source_filename: str | None = None,
) -> str:
    """
    Build a clean, editorial-style LaTeX document from OCR page texts.

    Charter body text, quiet small-caps running header, and a thin-rule
    page marker instead of loud colored section headings.
    """
    safe_title = escape_latex(title or "Vid2PDF Text Export")
    header_title = escape_latex(_shorten(title or "Vid2PDF Text Export", 60))
    subtitle = escape_latex(source_filename) if source_filename else None

    parts: list[str] = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[a4paper,top=2.6cm,bottom=3.0cm,left=2.7cm,right=2.7cm]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{charter}",
        r"\usepackage{microtype}",
        r"\usepackage{parskip}",
        r"\usepackage{ragged2e}",
        r"\usepackage{xcolor}",
        r"\usepackage{fancyhdr}",
        r"\usepackage{titlesec}",
        r"\usepackage{hyperref}",
        rf"\definecolor{{{ACCENT}}}{{HTML}}{{0F766E}}",
        rf"\definecolor{{{INK}}}{{HTML}}{{1A1F24}}",
        rf"\definecolor{{{MUTED}}}{{HTML}}{{6B7280}}",
        rf"\definecolor{{{RULE}}}{{HTML}}{{D8DEE4}}",
        rf"\hypersetup{{hidelinks,pdftitle={{{safe_title}}}}}",
        r"\color{" + INK + "}",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        rf"\fancyhead[L]{{\footnotesize\scshape\color{{{MUTED}}}{header_title}}}",
        rf"\fancyhead[R]{{\footnotesize\color{{{MUTED}}}\thepage}}",
        r"\renewcommand{\headrulewidth}{0pt}",
        r"\setlength{\headsep}{1.6em}",
        # Small-caps subheadings for detected in-page headings.
        rf"\titleformat{{\subsection}}{{\normalsize\bfseries\color{{{INK}}}}}{{}}{{0em}}{{}}",
        r"\titlespacing*{\subsection}{0pt}{1.1em}{0.35em}",
        # Quiet page marker: small-caps label over a hairline rule.
        r"\newcommand{\pagemarker}[1]{%",
        rf"  {{\footnotesize\scshape\color{{{MUTED}}}page~#1}}\\[0.2em]",
        rf"  {{\color{{{RULE}}}\rule{{\linewidth}}{{0.5pt}}}}\par\vspace{{0.9em}}}}",
        r"\setlength{\parskip}{0.55em}",
        # OCR text contains unbreakable junk tokens; stretch rather than overflow.
        r"\setlength{\emergencystretch}{3em}",
        r"\justifying",
        r"\begin{document}",
        r"\thispagestyle{empty}",
        r"\begin{flushleft}",
        rf"{{\LARGE\bfseries\color{{{INK}}} {safe_title}}}\\[0.6em]",
    ]
    if subtitle:
        parts.append(rf"{{\small\color{{{MUTED}}} Source: {subtitle}}}\\[0.25em]")
    parts.extend(
        [
            rf"{{\small\color{{{MUTED}}} Extracted with Vid2PDF\;\textperiodcentered\; {date.today():%B %d, %Y}}}\\[0.7em]",
            rf"{{\color{{{ACCENT}}}\rule{{2.4cm}}{{2pt}}}}",
            r"\end{flushleft}",
            r"\vspace{1.4em}",
        ]
    )

    for index, page in enumerate(pages):
        if index > 0:
            parts.append(r"\newpage")
        parts.append(rf"\pagemarker{{{page.page_number}}}")
        parts.append(_page_body(page))

    parts.append(r"\end{document}")
    return "\n".join(parts) + "\n"


def write_latex_file(tex_path: Path, latex_source: str) -> Path:
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(latex_source, encoding="utf-8")
    return tex_path


def _shorten(text: str, limit: int) -> str:
    compact = text.strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _page_body(page: PageText) -> str:
    if page.status == "failed":
        message = page.error or "OCR failed for this page."
        return rf"\textcolor{{{MUTED}}}{{\itshape {escape_latex(message)}}}"

    if page.status == "empty" or not page.raw_text.strip():
        if page.blocks:
            return _format_paragraphs([block.text for block in page.blocks if block.text.strip()])
        return rf"\textcolor{{{MUTED}}}{{\itshape {escape_latex(EMPTY_PAGE_PLACEHOLDER)}}}"

    # Prefer raw_text: it already groups lines into paragraphs by vertical
    # gaps, whereas blocks are individual OCR lines.
    paragraphs = [part.strip() for part in page.raw_text.split("\n\n") if part.strip()]
    if not paragraphs and page.blocks:
        paragraphs = [block.text for block in page.blocks if block.text.strip()]

    paragraphs = _merge_flowing_paragraphs(paragraphs)
    if not paragraphs:
        return rf"\textcolor{{{MUTED}}}{{\itshape {escape_latex(EMPTY_PAGE_PLACEHOLDER)}}}"

    return _format_paragraphs(paragraphs)


def _merge_flowing_paragraphs(paragraphs: list[str]) -> list[str]:
    """Merge short consecutive OCR lines into justified body paragraphs."""
    merged: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        text = clean_gibberish_text(" ".join(buffer))
        if text and (is_plausible_page_text(text) or len(text.split()) <= 8):
            merged.append(text)
        buffer = []

    for paragraph in paragraphs:
        text = clean_gibberish_text(paragraph.strip())
        if not text:
            continue
        if _looks_like_heading(text):
            flush()
            merged.append(text)
            continue
        # Start a new paragraph on clear sentence boundaries / long gaps.
        if buffer and (text[:1].isupper() and buffer[-1].endswith((".", "!", "?"))):
            flush()
        buffer.append(text)
        # Flush when we already have a substantial paragraph.
        if sum(len(part) for part in buffer) >= 420:
            flush()
    flush()
    return merged


def _format_paragraphs(paragraphs: list[str]) -> str:
    parts: list[str] = []
    for paragraph in paragraphs:
        text = paragraph.strip()
        if not text:
            continue
        if _looks_like_heading(text):
            parts.append(rf"\subsection*{{{escape_latex(text)}}}")
        else:
            parts.append(rf"{_escape_body_text(text)}\par")
    return "\n\n".join(parts)


def _escape_body_text(text: str) -> str:
    """Escape body text, letting very long tokens (URLs, OCR junk) wrap."""
    words: list[str] = []
    for token in text.split(" "):
        if len(token) > 24:
            chunks = [escape_latex(token[i : i + 16]) for i in range(0, len(token), 16)]
            words.append(r"\allowbreak{}".join(chunks))
        else:
            words.append(escape_latex(token))
    return " ".join(words)


def _looks_like_heading(text: str) -> bool:
    compact = clean_gibberish_text(text.strip())
    if len(compact) > 72 or len(compact) < 3:
        return False
    if not is_plausible_page_text(compact) and len(compact.split()) > 3:
        return False
    words = compact.split()
    # Reject noisy ALL-CAPS OCR garbage like "SS SS PS".
    if all(len(word) <= 3 for word in words) and len(words) >= 3:
        return False
    if compact.endswith(":") and len(compact) <= 48 and is_plausible_page_text(compact):
        return True
    letters = [char for char in compact if char.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    if upper_ratio >= 0.82 and len(words) <= 8 and is_plausible_page_text(compact):
        return True
    if 2 <= len(words) <= 8 and all(word[:1].isupper() for word in words if word[:1].isalpha()):
        vowel_ok = any(any(char.lower() in "aeiouy" for char in word) for word in words)
        return vowel_ok
    return False
