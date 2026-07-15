import io

import cv2
import numpy as np
from PIL import Image
from pypdf import PdfReader

from app.models.job import BlurRegion, DrawStroke, EditPoint, PageEdits
from app.processing.editor import apply_page_edits
from app.processing.exporter import export_pdf
from app.processing.types import FrameQuality, SampledFrame, SelectedPage


def _make_page(tmp_path, page_id: str, image: np.ndarray) -> SelectedPage:
    image_path = tmp_path / f"{page_id}.png"
    cv2.imwrite(str(image_path), image)
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
        text_density=0.1,
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
    frame = SampledFrame(timestamp=0.0, frame_index=0, image=image, quality=quality)
    return SelectedPage(
        page_id=page_id,
        page_number=1,
        label=page_id,
        source_segment_id=f"seg-{page_id}",
        segment_start=0.0,
        segment_end=1.0,
        selected_frame=frame,
        image_path=str(image_path),
        thumbnail_path=str(image_path),
    )


def _noisy_text_image() -> np.ndarray:
    rng = np.random.default_rng(7)
    image = rng.integers(120, 255, size=(220, 180, 3), dtype=np.uint8)
    cv2.putText(image, "Vid2PDF", (14, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)
    return image


def test_export_pdf_embeds_pages_losslessly(tmp_path) -> None:
    image = _noisy_text_image()
    pages = [_make_page(tmp_path, "page-a", image), _make_page(tmp_path, "page-b", image)]

    artifact = export_pdf("job-lossless", pages, str(tmp_path), title="Quality check")

    pdf_path = tmp_path / artifact.filename
    raw = pdf_path.read_bytes()
    assert b"/FlateDecode" in raw
    assert b"/DCTDecode" not in raw  # no JPEG re-encode anywhere

    reader = PdfReader(str(pdf_path))
    assert len(reader.pages) == 2

    # The embedded image must be pixel-identical to the source page PNG.
    embedded = reader.pages[0].images[0].image.convert("RGB")
    source = Image.open(pages[0].image_path).convert("RGB")
    assert np.array_equal(np.asarray(embedded), np.asarray(source))


def test_apply_page_edits_brightness_contrast(tmp_path) -> None:
    image = np.full((60, 60, 3), 100, dtype=np.uint8)
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), image)

    brighter = apply_page_edits(str(path), PageEdits(brightness=50))
    assert float(np.mean(brighter)) > 130

    darker = apply_page_edits(str(path), PageEdits(brightness=-50))
    assert float(np.mean(darker)) < 70

    # Positive contrast pushes a below-mid gray further down.
    contrasty = apply_page_edits(str(path), PageEdits(contrast=80))
    assert float(np.mean(contrasty)) < float(np.mean(image))

    unchanged = apply_page_edits(str(path), PageEdits())
    assert np.array_equal(unchanged, image)


def test_apply_page_edits_fill_region_redacts(tmp_path) -> None:
    image = np.full((80, 80, 3), 200, dtype=np.uint8)
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), image)

    edited = apply_page_edits(
        str(path),
        PageEdits(
            blur_regions=[
                BlurRegion(x=10, y=10, width=30, height=20, mode="fill", fill_color="#000000")
            ]
        ),
    )
    assert np.all(edited[10:30, 10:40] == 0)
    assert np.all(edited[50:, 50:] == 200)


def test_apply_page_edits_highlight_stroke_is_translucent(tmp_path) -> None:
    image = np.full((80, 120, 3), 255, dtype=np.uint8)
    cv2.putText(image, "ABC", (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), image)

    edited = apply_page_edits(
        str(path),
        PageEdits(
            strokes=[
                DrawStroke(
                    color="#facc15",
                    width=24,
                    points=[EditPoint(x=5, y=38), EditPoint(x=115, y=38)],
                    opacity=0.35,
                )
            ]
        ),
    )

    band = edited[30:46, 10:110]
    # The band is tinted (no longer pure white anywhere) ...
    assert float(np.mean(band[:, :, 0])) < 250  # blue channel drops under yellow
    # ... but the dark text underneath must still be visible through it.
    assert int(np.count_nonzero(np.mean(band, axis=2) < 120)) > 50
