from __future__ import annotations

from pathlib import Path

import cv2

from app.processing.document import normalize_final_page
from app.processing.types import PipelineContext, SelectedPage


def attach_previews(
    pages: list[SelectedPage],
    context: PipelineContext,
) -> list[SelectedPage]:
    page_dir = Path(context.page_dir)
    thumbnail_dir = Path(context.thumbnail_dir)
    page_dir.mkdir(parents=True, exist_ok=True)
    thumbnail_dir.mkdir(parents=True, exist_ok=True)

    for page in pages:
        image_filename = f"{page.page_id}.png"
        thumb_filename = f"{page.page_id}-thumb.jpg"
        image_path = page_dir / image_filename
        thumbnail_path = thumbnail_dir / thumb_filename

        output_image = page.selected_frame.image
        if output_image is None:
            continue
        if context.processing_mode == "camera":
            output_image = normalize_final_page(output_image)
        page.selected_frame.image = output_image

        cv2.imwrite(str(image_path), output_image)
        thumbnail_image = _build_thumbnail(output_image)
        cv2.imwrite(str(thumbnail_path), thumbnail_image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])

        page.image_path = str(image_path)
        page.thumbnail_path = str(thumbnail_path)
        page.image_url = f"{context.artifact_base_url}/jobs/{context.job_id}/pages/{image_filename}"
        page.preview_url = f"{context.artifact_base_url}/jobs/{context.job_id}/thumbnails/{thumb_filename}"

    return pages


def _build_thumbnail(image):
    height, width = image.shape[:2]
    target_width = 360
    scale = target_width / max(width, 1)
    target_height = max(int(height * scale), 1)
    return cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)
