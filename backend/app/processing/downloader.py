from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


def is_valid_video_url(url: str) -> bool:
    return bool(_URL_PATTERN.match(url.strip()))


def download_video(url: str, output_dir: str, job_id: str) -> tuple[str, str]:
    """
    Download a video from a URL (YouTube or any yt-dlp-supported site, plus
    direct video links) into the uploads directory.

    Returns (file_path, display_title).
    """
    import yt_dlp

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    output_template = str(output_root / f"{job_id}-%(title).80B.%(ext)s")

    # Without ffmpeg, merging separate video+audio streams fails, so prefer
    # progressive formats in that case. We only need the video track anyway.
    has_ffmpeg = shutil.which("ffmpeg") is not None
    if has_ffmpeg:
        format_spec = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    else:
        format_spec = "best[height<=1080][ext=mp4]/best[height<=720]/best"

    options = {
        "format": format_spec,
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": 2 * 1024 * 1024 * 1024,  # 2 GB guard
        "restrictfilenames": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise ValueError("Could not download a video from that URL.")
        # requested_downloads carries the final path after any post-processing.
        downloads = info.get("requested_downloads") or []
        if downloads and downloads[0].get("filepath"):
            file_path = downloads[0]["filepath"]
        else:
            file_path = ydl.prepare_filename(info)
        title = info.get("title") or Path(file_path).stem

    if not Path(file_path).is_file():
        raise ValueError("Download finished but the video file was not found.")

    logger.info("Downloaded video for job=%s from %s -> %s", job_id, url, file_path)
    return str(file_path), str(title)
