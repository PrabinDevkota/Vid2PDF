from __future__ import annotations

import cv2
import numpy as np

from app.processing.types import DocumentDetection


def detect_document_region(frame: np.ndarray) -> DocumentDetection:
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 60, 180)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_contour = None
    best_score = 0.0

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < (width * height * 0.18):
            continue
        perimeter = cv2.arcLength(contour, True)
        approximation = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approximation) != 4 or not cv2.isContourConvex(approximation):
            rectangle = cv2.minAreaRect(contour)
            approximation = cv2.boxPoints(rectangle).reshape(4, 1, 2).astype(np.int32)

        bounding_x, bounding_y, bounding_w, bounding_h = cv2.boundingRect(approximation)
        bounding_area = max(bounding_w * bounding_h, 1)
        rectangularity = float(area / bounding_area)
        score = (area / (width * height)) * 0.75 + rectangularity * 0.25
        if score > best_score:
            best_score = score
            best_contour = approximation

    if best_contour is None:
        return DocumentDetection(
            found=False,
            contour=None,
            corrected_image=frame,
            page_coverage=0.0,
            rectangularity=0.0,
            occlusion_ratio=_estimate_occlusion(frame),
            perspective_score=0.0,
        )

    ordered_corners = _order_points(best_contour.reshape(4, 2).astype("float32"))
    corrected = crop_document_image(_warp_document(frame, ordered_corners))
    page_coverage = float(cv2.contourArea(best_contour) / (width * height))
    bounding_x, bounding_y, bounding_w, bounding_h = cv2.boundingRect(best_contour)
    rectangularity = float(
        cv2.contourArea(best_contour) / max(bounding_w * bounding_h, 1)
    )
    perspective_score = _perspective_score(ordered_corners)

    return DocumentDetection(
        found=True,
        contour=best_contour,
        corrected_image=corrected,
        page_coverage=page_coverage,
        rectangularity=rectangularity,
        occlusion_ratio=_estimate_occlusion(corrected),
        perspective_score=perspective_score,
    )


def normalize_final_page(image: np.ndarray) -> np.ndarray:
    cropped_image = crop_document_image(image)
    gray = cv2.cvtColor(cropped_image, cv2.COLOR_BGR2GRAY)
    cropped = _crop_dark_borders(gray)
    denoised = cv2.fastNlMeansDenoising(cropped, None, 8, 7, 21)
    flattened = _flatten_background(denoised)
    contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(flattened)
    normalized = cv2.adaptiveThreshold(
        contrast,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        11,
    )
    normalized = _remove_border_connected_dark_regions(normalized)
    normalized = cv2.medianBlur(normalized, 3)
    normalized = cv2.morphologyEx(
        normalized,
        cv2.MORPH_OPEN,
        np.ones((2, 2), np.uint8),
        iterations=1,
    )

    white_ratio = float(np.mean(normalized > 0))
    if white_ratio < 0.5:
        normalized = cv2.bitwise_not(normalized)
        white_ratio = float(np.mean(normalized > 0))

    # If thresholding still produced an overly dark/noisy page, fall back to a
    # softened grayscale rendering instead of exporting a near-black page.
    if white_ratio < 0.7:
        normalized = cv2.normalize(contrast, None, 135, 255, cv2.NORM_MINMAX)

    bordered = cv2.copyMakeBorder(
        normalized,
        20,
        20,
        20,
        20,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    return cv2.cvtColor(bordered, cv2.COLOR_GRAY2BGR)


def crop_document_image(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    if height < 80 or width < 80:
        return image

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    page_mask = _build_page_mask(gray, saturation, value)
    cropped = _crop_from_mask(image, page_mask)
    if cropped is not None:
        return cropped

    fallback_mask = _build_fallback_mask(gray)
    fallback_cropped = _crop_from_mask(image, fallback_mask)
    return fallback_cropped if fallback_cropped is not None else image


def _warp_document(frame: np.ndarray, corners: np.ndarray) -> np.ndarray:
    top_left, top_right, bottom_right, bottom_left = corners
    width_a = np.linalg.norm(bottom_right - bottom_left)
    width_b = np.linalg.norm(top_right - top_left)
    height_a = np.linalg.norm(top_right - bottom_right)
    height_b = np.linalg.norm(top_left - bottom_left)

    max_width = int(max(width_a, width_b))
    max_height = int(max(height_a, height_b))

    destination = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype="float32",
    )
    transform = cv2.getPerspectiveTransform(corners, destination)
    warped = cv2.warpPerspective(
        frame,
        transform,
        (max_width, max_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return warped


def _order_points(points: np.ndarray) -> np.ndarray:
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1)
    top_left = points[np.argmin(sums)]
    bottom_right = points[np.argmax(sums)]
    top_right = points[np.argmin(diffs)]
    bottom_left = points[np.argmax(diffs)]
    return np.array([top_left, top_right, bottom_right, bottom_left], dtype="float32")


def _perspective_score(corners: np.ndarray) -> float:
    top_left, top_right, bottom_right, bottom_left = corners
    horizontal_top = np.linalg.norm(top_right - top_left)
    horizontal_bottom = np.linalg.norm(bottom_right - bottom_left)
    vertical_left = np.linalg.norm(bottom_left - top_left)
    vertical_right = np.linalg.norm(bottom_right - top_right)
    horizontal_balance = 1.0 - min(abs(horizontal_top - horizontal_bottom) / max(horizontal_top, 1.0), 1.0)
    vertical_balance = 1.0 - min(abs(vertical_left - vertical_right) / max(vertical_left, 1.0), 1.0)
    return float((horizontal_balance + vertical_balance) / 2.0)


def _estimate_occlusion(image: np.ndarray) -> float:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower_skin = np.array([0, 25, 60], dtype=np.uint8)
    upper_skin = np.array([25, 180, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower_skin, upper_skin)
    return float(np.mean(mask > 0))


def _flatten_background(gray: np.ndarray) -> np.ndarray:
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=21, sigmaY=21)
    background = np.maximum(background, 1)
    return cv2.divide(gray, background, scale=255)


def _crop_dark_borders(gray: np.ndarray) -> np.ndarray:
    mask = gray > 16
    if not np.any(mask):
        return gray

    coordinates = np.column_stack(np.where(mask))
    top, left = coordinates.min(axis=0)
    bottom, right = coordinates.max(axis=0)

    if (bottom - top) < 40 or (right - left) < 40:
        return gray

    padding = 8
    top = max(int(top) - padding, 0)
    left = max(int(left) - padding, 0)
    bottom = min(int(bottom) + padding, gray.shape[0] - 1)
    right = min(int(right) + padding, gray.shape[1] - 1)
    return gray[top : bottom + 1, left : right + 1]


def _remove_border_connected_dark_regions(binary: np.ndarray) -> np.ndarray:
    inverted = cv2.bitwise_not(binary)
    height, width = inverted.shape[:2]
    components = (inverted > 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(components, connectivity=8)
    cleaned = np.zeros_like(inverted)

    for label in range(1, count):
        x, y, component_width, component_height, _ = stats[label]
        touches_border = (
            x == 0
            or y == 0
            or (x + component_width) >= width
            or (y + component_height) >= height
        )
        if touches_border:
            continue
        cleaned[labels == label] = 255

    return cv2.bitwise_not(cleaned)


def _build_page_mask(gray: np.ndarray, saturation: np.ndarray, value: np.ndarray) -> np.ndarray:
    brightness_threshold = int(np.clip(np.percentile(gray, 72), 120, 245))
    saturation_threshold = int(np.clip(np.percentile(saturation, 55), 26, 110))
    value_threshold = int(np.clip(np.percentile(value, 70), 120, 245))

    bright_mask = gray >= brightness_threshold
    low_saturation_mask = saturation <= saturation_threshold
    page_mask = np.where(bright_mask & low_saturation_mask & (value >= value_threshold), 255, 0).astype(np.uint8)
    return _stabilize_mask(page_mask)


def _build_fallback_mask(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresholded = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    border_ratio = _border_white_ratio(thresholded)
    if border_ratio > 0.7:
        thresholded = cv2.bitwise_not(thresholded)

    return _stabilize_mask(thresholded)


def _stabilize_mask(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape[:2]
    kernel_size = max(5, int(round(min(height, width) * 0.03)))
    if kernel_size % 2 == 0:
        kernel_size += 1

    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    open_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(3, kernel_size // 3), max(3, kernel_size // 3)),
    )
    stabilized = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=1)
    stabilized = cv2.morphologyEx(stabilized, cv2.MORPH_OPEN, open_kernel, iterations=1)
    return stabilized


def _crop_from_mask(image: np.ndarray, mask: np.ndarray) -> np.ndarray | None:
    height, width = image.shape[:2]
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    image_area = height * width
    best_bounds = None
    best_score = 0.0

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * 0.35:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        bounding_area = max(w * h, 1)
        fill_ratio = float(area / bounding_area)
        coverage = float(area / image_area)
        aspect_ratio = w / max(h, 1)
        if aspect_ratio < 0.45 or aspect_ratio > 1.9:
            continue
        if fill_ratio < 0.7:
            continue

        score = (coverage * 0.7) + (fill_ratio * 0.3)
        if score > best_score:
            best_score = score
            best_bounds = (x, y, w, h)

    if best_bounds is None:
        return None

    x, y, w, h = best_bounds
    padding = max(10, int(round(min(height, width) * 0.02)))
    left = max(x - padding, 0)
    top = max(y - padding, 0)
    right = min(x + w + padding, width)
    bottom = min(y + h + padding, height)

    cropped_width = right - left
    cropped_height = bottom - top
    if cropped_width < width * 0.45 or cropped_height < height * 0.45:
        return None

    return image[top:bottom, left:right]


def _border_white_ratio(mask: np.ndarray, border_size: int = 12) -> float:
    height, width = mask.shape[:2]
    border_size = max(1, min(border_size, height // 4, width // 4))
    border_pixels = np.concatenate(
        [
            mask[:border_size, :].ravel(),
            mask[-border_size:, :].ravel(),
            mask[:, :border_size].ravel(),
            mask[:, -border_size:].ravel(),
        ]
    )
    return float(np.mean(border_pixels > 0))
