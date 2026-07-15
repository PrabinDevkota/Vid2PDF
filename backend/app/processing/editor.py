from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.models.job import BlurRegion, CropBox, DrawStroke, PageEdits, TextAnnotation


def apply_page_edits(source_image_path: str, edits: PageEdits) -> np.ndarray:
    source = cv2.imread(source_image_path)
    if source is None:
        raise ValueError(f"Could not read source page image: {source_image_path}")

    image = _rotate(source, edits.rotation)
    image = _crop(image, edits.crop)
    image = _apply_adjustments(image, edits.brightness, edits.contrast)
    image = _apply_filter(image, edits.filter)
    image = _apply_blur_regions(image, edits.blur_regions)
    image = _apply_draw_and_text(image, edits.strokes, edits.texts)
    return image


def write_rendered_page(
    source_image_path: str,
    output_image_path: str,
    thumbnail_path: str,
    edits: PageEdits,
) -> None:
    image = apply_page_edits(source_image_path, edits)
    output_path = Path(output_image_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    thumb_path = Path(thumbnail_path)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    cv2.imwrite(str(output_path), image)
    thumbnail = build_thumbnail(image)
    cv2.imwrite(str(thumb_path), thumbnail, [int(cv2.IMWRITE_JPEG_QUALITY), 88])


def build_thumbnail(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    target_width = 360
    scale = target_width / max(width, 1)
    target_height = max(int(height * scale), 1)
    return cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)


def rotate_image(image: np.ndarray, rotation: int) -> np.ndarray:
    """Rotate by a multiple of 90°, matching how page edits are applied."""
    return _rotate(image, rotation)


def _rotate(image: np.ndarray, rotation: int) -> np.ndarray:
    turns = (rotation % 360) // 90
    if turns == 1:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if turns == 2:
        return cv2.rotate(image, cv2.ROTATE_180)
    if turns == 3:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image


def _crop(image: np.ndarray, crop: CropBox | None) -> np.ndarray:
    if crop is None:
        return image
    height, width = image.shape[:2]
    x = max(0, min(crop.x, width - 1))
    y = max(0, min(crop.y, height - 1))
    crop_width = max(1, min(crop.width, width - x))
    crop_height = max(1, min(crop.height, height - y))
    return image[y : y + crop_height, x : x + crop_width]


def _apply_adjustments(image: np.ndarray, brightness: int, contrast: int) -> np.ndarray:
    """Centered brightness/contrast, mirroring the editor's live preview math."""
    brightness = max(-100, min(100, brightness))
    contrast = max(-100, min(100, contrast))
    if brightness == 0 and contrast == 0:
        return image
    # contrast -100..100 -> gain 0.2..1.8 around the mid-gray point.
    gain = 1.0 + (contrast / 100.0) * 0.8
    offset = brightness * 0.8
    lut = np.clip((np.arange(256, dtype=np.float32) - 128.0) * gain + 128.0 + offset, 0, 255)
    return cv2.LUT(image, lut.astype(np.uint8))


def _apply_filter(image: np.ndarray, page_filter: str) -> np.ndarray:
    if page_filter == "grayscale":
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    if page_filter == "bw":
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            15,
        )
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    if page_filter == "enhance":
        # Illumination correction ("magic color"): divide each channel by its
        # blurred background so paper turns white and shadows disappear.
        height, width = image.shape[:2]
        kernel = max(31, (max(height, width) // 20) | 1)
        background = cv2.GaussianBlur(image, (kernel, kernel), 0)
        normalized = cv2.divide(image, background, scale=255)
        # Mild contrast boost so ink stays dark after normalization.
        return cv2.convertScaleAbs(normalized, alpha=1.12, beta=-14)

    return image


def _apply_blur_regions(image: np.ndarray, regions: list[BlurRegion]) -> np.ndarray:
    if not regions:
        return image
    output = image.copy()
    height, width = image.shape[:2]
    for region in regions:
        x = max(0, min(region.x, width - 1))
        y = max(0, min(region.y, height - 1))
        region_width = max(1, min(region.width, width - x))
        region_height = max(1, min(region.height, height - y))
        if region.mode == "fill":
            output[y : y + region_height, x : x + region_width] = _hex_to_bgr(
                region.fill_color
            )
            continue
        patch = output[y : y + region_height, x : x + region_width]
        kernel = max(3, region.intensity | 1)
        output[y : y + region_height, x : x + region_width] = cv2.GaussianBlur(
            patch,
            (kernel, kernel),
            0,
        )
    return output


def _hex_to_bgr(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) != 6:
        return (0, 0, 0)
    try:
        red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (0, 0, 0)
    return (blue, green, red)


def _apply_draw_and_text(
    image: np.ndarray,
    strokes: list[DrawStroke],
    texts: list[TextAnnotation],
) -> np.ndarray:
    if not strokes and not texts:
        return image

    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb_image)
    font = _load_font()

    translucent = [
        stroke for stroke in strokes if stroke.opacity < 1.0 and len(stroke.points) >= 2
    ]
    if translucent:
        # Highlighter strokes: draw on a transparent overlay so overlapping
        # segments of one stroke blend once, then alpha-composite.
        overlay = Image.new("RGBA", pil_image.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for stroke in translucent:
            alpha = max(0, min(255, int(round(stroke.opacity * 255))))
            points = [(point.x, point.y) for point in stroke.points]
            overlay_draw.line(
                points,
                fill=_hex_to_rgba(stroke.color, alpha),
                width=max(1, stroke.width),
                joint="curve",
            )
        pil_image = Image.alpha_composite(pil_image.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(pil_image)
    for stroke in strokes:
        if stroke.opacity < 1.0 or len(stroke.points) < 2:
            continue
        points = [(point.x, point.y) for point in stroke.points]
        draw.line(points, fill=stroke.color, width=max(1, stroke.width), joint="curve")

    for annotation in texts:
        draw.text(
            (annotation.x, annotation.y),
            annotation.text,
            fill=annotation.color,
            font=_font_with_size(font, annotation.font_size),
        )

    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


def _hex_to_rgba(color: str, alpha: int) -> tuple[int, int, int, int]:
    value = color.lstrip("#")
    if len(value) != 6:
        return (250, 204, 21, alpha)
    try:
        red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (250, 204, 21, alpha)
    return (red, green, blue, alpha)


def _load_font() -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    candidate_paths = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidate_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=24)
            except OSError:
                continue
    return ImageFont.load_default()


def _font_with_size(font: ImageFont.ImageFont | ImageFont.FreeTypeFont, size: int):
    if isinstance(font, ImageFont.FreeTypeFont):
        return font.font_variant(size=max(10, size))
    return font
