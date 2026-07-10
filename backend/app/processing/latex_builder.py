from __future__ import annotations

import re
from pathlib import Path

from app.processing.ocr import PageText

EMPTY_PAGE_PLACEHOLDER = "[No text detected on this page]"
ACCENT = "VidAccent"
MUTED = "VidMuted"
RULE = "VidRule"
WARN = "VidWarn"


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
    """Build a complete LaTeX article from OCR page texts with teal accents."""
    safe_title = escape_latex(title or "Vid2PDF Text Export")
    subtitle = escape_latex(source_filename) if source_filename else None

    parts: list[str] = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        r"\usepackage{setspace}",
        r"\usepackage{hyperref}",
        r"\usepackage{fancyhdr}",
        r"\usepackage[dvipsnames,svgnames,table]{xcolor}",
        r"\usepackage{titlesec}",
        r"\definecolor{VidAccent}{HTML}{0F766E}",
        r"\definecolor{VidMuted}{HTML}{5B6B7A}",
        r"\definecolor{VidRule}{HTML}{C5D0DC}",
        r"\definecolor{VidWarn}{HTML}{94610F}",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        rf"\fancyhead[L]{{\textcolor{{{ACCENT}}}{{\textbf{{{safe_title}}}}}}}",
        rf"\fancyhead[R]{{\textcolor{{{MUTED}}}{{\thepage}}}}",
        r"\renewcommand{\headrulewidth}{0.6pt}",
        rf"\renewcommand{{\headrule}}{{\hbox to\headwidth{{\color{{{ACCENT}}}\leaders\hrule height \headrulewidth\hfill}}}}",
        rf"\titleformat{{\section}}{{\Large\bfseries\color{{{ACCENT}}}}}{{}}{{0em}}{{}}[\vspace{{0.2em}}{{\color{{{RULE}}}\titlerule}}]",
        rf"\titleformat{{\subsection}}{{\large\bfseries\color{{{ACCENT}}}}}{{}}{{0em}}{{}}",
        r"\setlength{\parskip}{0.65em}",
        r"\setlength{\parindent}{0pt}",
        r"\onehalfspacing",
        r"\begin{document}",
        r"\begin{center}",
        rf"{{\Huge\bfseries\color{{{ACCENT}}} {safe_title}}}\\[0.45em]",
        rf"{{\large\color{{{MUTED}}} Vid2PDF}}\\[0.7em]",
        rf"{{\color{{{RULE}}}\rule{{0.65\linewidth}}{{0.9pt}}}}",
        r"\end{center}",
        r"\vspace{0.8em}",
    ]
    if subtitle:
        parts.append(
            rf"\noindent\textcolor{{{MUTED}}}{{\textit{{Source: {subtitle}}}}}"
        )
        parts.append(r"\vspace{1.1em}")

    for index, page in enumerate(pages):
        if index > 0:
            parts.append(r"\newpage")

        parts.append(rf"\section*{{Page {page.page_number}}}")
        parts.append(r"\vspace{0.35em}")
        parts.append(_page_body(page))

    parts.append(r"\end{document}")
    return "\n".join(parts) + "\n"


def write_latex_file(tex_path: Path, latex_source: str) -> Path:
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(latex_source, encoding="utf-8")
    return tex_path


def _page_body(page: PageText) -> str:
    if page.status == "failed":
        message = page.error or "OCR failed for this page."
        return rf"\textcolor{{{WARN}}}{{\textit{{{escape_latex(message)}}}}}"

    if page.status == "empty" or not page.raw_text.strip():
        if page.blocks:
            return _format_paragraphs([block.text for block in page.blocks if block.text.strip()])
        return rf"\textcolor{{{WARN}}}{{\textit{{{escape_latex(EMPTY_PAGE_PLACEHOLDER)}}}}}"

    if page.blocks:
        paragraphs = [block.text for block in page.blocks if block.text.strip()]
    else:
        paragraphs = [part.strip() for part in page.raw_text.split("\n\n") if part.strip()]

    if not paragraphs:
        return rf"\textcolor{{{WARN}}}{{\textit{{{escape_latex(EMPTY_PAGE_PLACEHOLDER)}}}}}"

    return _format_paragraphs(paragraphs)


def _format_paragraphs(paragraphs: list[str]) -> str:
    parts: list[str] = []
    for paragraph in paragraphs:
        text = paragraph.strip()
        if not text:
            continue
        if _looks_like_heading(text):
            parts.append(
                rf"\subsection*{{\textcolor{{{ACCENT}}}{{{escape_latex(text)}}}}}"
            )
        else:
            parts.append(rf"{escape_latex(text)}\par")
    return "\n\n".join(parts)


def _looks_like_heading(text: str) -> bool:
    compact = text.strip()
    if len(compact) > 72 or len(compact) < 3:
        return False
    if compact.endswith(":") and len(compact) <= 48:
        return True
    letters = [char for char in compact if char.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    if upper_ratio >= 0.82 and len(compact.split()) <= 10:
        return True
    words = compact.split()
    if 2 <= len(words) <= 8 and all(word[:1].isupper() for word in words if word[:1].isalpha()):
        return True
    return False
