import cv2
import numpy as np

from app.processing.document import crop_document_image, normalize_final_page


def _build_document_scene() -> np.ndarray:
    image = np.full((420, 320, 3), (58, 82, 106), dtype=np.uint8)
    cv2.rectangle(image, (42, 36), (276, 384), (244, 243, 238), thickness=-1)
    cv2.rectangle(image, (42, 36), (276, 384), (214, 214, 214), thickness=3)

    # Simulate printed content placed close to the page edges. The crop should
    # preserve these marks rather than trimming them away with the background.
    cv2.rectangle(image, (58, 54), (250, 70), (20, 20, 20), thickness=-1)
    cv2.rectangle(image, (58, 332), (246, 346), (25, 25, 25), thickness=-1)
    cv2.rectangle(image, (56, 88), (72, 324), (30, 30, 30), thickness=-1)
    cv2.rectangle(image, (246, 88), (262, 324), (35, 35, 35), thickness=-1)
    return image


def test_crop_document_image_removes_outer_background_and_keeps_edge_content() -> None:
    image = _build_document_scene()

    cropped = crop_document_image(image)

    assert cropped.shape[0] < image.shape[0]
    assert cropped.shape[1] < image.shape[1]

    # The cropped image should now start on the page itself rather than the desk.
    corner_patch = cropped[:18, :18]
    assert float(np.mean(corner_patch)) > 205

    # Edge-adjacent page content should still exist after cropping.
    top_band = cropped[:40, :]
    left_band = cropped[:, :40]
    assert np.count_nonzero(np.mean(top_band, axis=2) < 90) > 100
    assert np.count_nonzero(np.mean(left_band, axis=2) < 90) > 100


def test_normalize_final_page_uses_the_refined_document_crop() -> None:
    image = _build_document_scene()

    normalized = normalize_final_page(image)

    # Normalization adds a white border, but the underlying document should
    # remain tightly cropped and free of the original desk background.
    assert normalized.shape[0] < image.shape[0]
    assert normalized.shape[1] < image.shape[1]
    assert float(np.mean(normalized[:12, :12])) > 240
