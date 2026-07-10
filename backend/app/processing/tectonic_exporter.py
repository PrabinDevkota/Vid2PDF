from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.settings import settings
from app.processing.latex_builder import build_latex_document, write_latex_file
from app.processing.ocr import PageText

logger = logging.getLogger(__name__)


@dataclass
class TextExportArtifact:
    filename: str
    download_url: str | None
    page_count: int
    tex_path: str | None = None


def ensure_tectonic_available() -> str:
    """Resolve the Tectonic binary even if the process PATH is stale."""
    candidates: list[str] = []
    cmd = (settings.tectonic_cmd or "tectonic").strip()
    candidates.append(cmd)

    which = shutil.which(cmd)
    if which:
        candidates.append(which)

    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates.extend(
        [
            str(local_app_data / "Programs" / "tectonic" / "tectonic.exe"),
            str(Path.home() / "AppData" / "Local" / "Programs" / "tectonic" / "tectonic.exe"),
            r"C:\Program Files\tectonic\tectonic.exe",
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if path.is_file():
            return str(path.resolve())
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    raise RuntimeError(
        f"Tectonic compiler `{cmd}` was not found on PATH. "
        "Install Tectonic (https://tectonic-typesetting.github.io/) "
        "and ensure it is available, or set settings.tectonic_cmd to the full "
        r"path (e.g. C:\Users\<you>\AppData\Local\Programs\tectonic\tectonic.exe)."
    )


def compile_latex_with_tectonic(
    *,
    job_id: str,
    title: str,
    pages: list[PageText],
    output_dir: str,
    source_filename: str | None = None,
) -> TextExportArtifact:
    """Write LaTeX and compile to PDF with Tectonic."""
    tectonic = ensure_tectonic_available()
    output_root = Path(output_dir)
    work_dir = output_root / f"{job_id}-text"
    work_dir.mkdir(parents=True, exist_ok=True)

    tex_name = f"{job_id}-text.tex"
    tex_path = work_dir / tex_name
    latex_source = build_latex_document(
        title=title,
        pages=pages,
        source_filename=source_filename,
    )
    write_latex_file(tex_path, latex_source)

    pdf_filename = f"{job_id}-text.pdf"
    pdf_path = output_root / pdf_filename

    try:
        result = subprocess.run(
            [
                tectonic,
                "--outdir",
                str(output_root),
                str(tex_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Tectonic compilation timed out after 180 seconds.") from exc

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        logger.error("Tectonic failed for job=%s: %s", job_id, stderr)
        raise RuntimeError(
            "Tectonic failed to compile the text PDF. "
            f"Details: {stderr[:800] or 'no output'}"
        )

    # Tectonic names output from the .tex stem
    produced = output_root / f"{job_id}-text.pdf"
    if not produced.exists():
        # Some versions write next to the tex file
        alt = work_dir / f"{job_id}-text.pdf"
        if alt.exists():
            alt.replace(pdf_path)
        else:
            raise RuntimeError("Tectonic completed but the PDF artifact was not found.")
    elif produced != pdf_path:
        produced.replace(pdf_path)

    return TextExportArtifact(
        filename=pdf_filename,
        download_url=None,
        page_count=len(pages),
        tex_path=str(tex_path),
    )
