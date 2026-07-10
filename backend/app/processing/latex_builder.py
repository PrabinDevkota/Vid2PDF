from __future__ import annotations

import re
from pathlib import Path

from app.processing.ocr import PageText

EMPTY_PAGE_PLACEHOLDER = "[No text detected on this page]"


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
    """Build a complete LaTeX article from OCR page texts."""
    safe_title = escape_latex(title or "Vid2PDF Text Export")
    subtitle = escape_latex(source_filename) if source_filename else None

    parts: list[str] = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{lmodern}",
        r"\usepackage{setspace}",
        r"\usepackage{hyperref}",
        r"\usepackage{fancyhdr}",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        rf"\fancyhead[L]{{{safe_title}}}",
        r"\fancyhead[R]{\thepage}",
        r"\renewcommand{\headrulewidth}{0.4pt}",
        r"\onehalfspacing",
        r"\begin{document}",
        rf"\title{{{safe_title}}}",
        r"\author{Vid2PDF}",
        r"\date{}",
        r"\maketitle",
    ]
    if subtitle:
        parts.append(rf"\noindent\textit{{Source: {subtitle}}}")
        parts.append(r"\vspace{1em}")

    for index, page in enumerate(pages):
        if index > 0:
            parts.append(r"\newpage")

        parts.append(rf"\section*{{Page {page.page_number}}}")
        parts.append(r"\vspace{0.5em}")

        body = _page_body(page)
        parts.append(body)

    parts.append(r"\end{document}")
    return "\n".join(parts) + "\n"


def write_latex_file(tex_path: Path, latex_source: str) -> Path:
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(latex_source, encoding="utf-8")
    return tex_path


def _page_body(page: PageText) -> str:
    if page.status == "failed":
        message = page.error or "OCR failed for this page."
        return rf"\textit{{{escape_latex(message)}}}"

    if page.status == "empty" or not page.raw_text.strip():
        if page.blocks:
            paragraphs = [block.text for block in page.blocks if block.text.strip()]
            if paragraphs:
                return "\n\n".join(
                    rf"\noindent {escape_latex(paragraph)}\par"
                    for paragraph in paragraphs
                )
        return rf"\textit{{{escape_latex(EMPTY_PAGE_PLACEHOLDER)}}}"

    # Prefer structured blocks when available; fall back to raw paragraphs
    if page.blocks:
        paragraphs = [block.text for block in page.blocks if block.text.strip()]
    else:
        paragraphs = [part.strip() for part in page.raw_text.split("\n\n") if part.strip()]

    if not paragraphs:
        return rf"\textit{{{escape_latex(EMPTY_PAGE_PLACEHOLDER)}}}"

    return "\n\n".join(
        rf"\noindent {escape_latex(paragraph)}\par" for paragraph in paragraphs
    )
