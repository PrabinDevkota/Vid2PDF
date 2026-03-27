from __future__ import annotations

import cv2
import numpy as np

from app.processing.types import DocumentDetection

EXPECTED_PAGE_ASPECT_RATIO = 0.72


def detect_document_region(frame: np.ndarray) -> DocumentDetection:
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 60, 180)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_contour = None
    best_score = 0.0
    best_metrics = None
    competing_score = 0.0

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
        page_coverage = float(area / (width * height))
        border_touch_ratio = _border_touch_ratio(
            bounding_x,
            bounding_y,
            bounding_w,
            bounding_h,
            width,
            height,
        )
        aspect_ratio = bounding_w / max(bounding_h, 1)
        single_page_score = _single_page_shape_score(aspect_ratio, border_touch_ratio)
        score = (
            (page_coverage * 0.45)
            + (rectangularity * 0.25)
            + (single_page_score * 0.2)
            + ((1.0 - border_touch_ratio) * 0.1)
        )
        if score > best_score:
            competing_score = best_score
            best_score = score
            best_contour = approximation
            best_metrics = (
                page_coverage,
                rectangularity,
                border_touch_ratio,
                single_page_score,
            )
        elif score > competing_score:
            competing_score = score

    if best_contour is None:
        return DocumentDetection(
            found=False,
            contour=None,
            corrected_image=frame,
            page_coverage=0.0,
            rectangularity=0.0,
            occlusion_ratio=_estimate_occlusion(frame),
            perspective_score=0.0,
            single_page_score=0.0,
            background_intrusion_ratio=1.0,
            border_touch_ratio=1.0,
            text_density=_text_density(frame),
            contour_confidence=0.0,
            gutter_ratio=1.0,
            opposing_page_ratio=1.0,
            normalized=False,
        )

    ordered_corners = _order_points(best_contour.reshape(4, 2).astype("float32"))
    corrected = crop_document_image(_warp_document(frame, ordered_corners))
    page_coverage, rectangularity, border_touch_ratio, single_page_score = best_metrics
    perspective_score = _perspective_score(ordered_corners)
    background_intrusion_ratio = _background_intrusion_ratio(corrected)
    text_density = _text_density(corrected)
    contour_confidence = _contour_confidence(
        page_coverage=page_coverage,
        rectangularity=rectangularity,
        perspective_score=perspective_score,
        border_touch_ratio=border_touch_ratio,
    )
    gutter_ratio = _gutter_ratio(corrected)
    opposing_page_ratio = _opposing_page_ratio(corrected)
    competing_penalty = min(competing_score / max(best_score, 0.001), 1.0)
    single_page_score = max(
        single_page_score
        - (competing_penalty * 0.35)
        - min(gutter_ratio * 1.2, 0.35)
        - min(opposing_page_ratio * 0.9, 0.35),
        0.0,
    )
    normalized = (
        page_coverage >= 0.42
        and rectangularity >= 0.62
        and border_touch_ratio <= 0.18
        and background_intrusion_ratio <= 0.2
        and single_page_score >= 0.58
        and contour_confidence >= 0.62
        and gutter_ratio <= 0.11
        and opposing_page_ratio <= 0.2
    )

    return DocumentDetection(
        found=True,
        contour=best_contour,
        corrected_image=corrected,
        page_coverage=page_coverage,
        rectangularity=rectangularity,
        occlusion_ratio=_estimate_occlusion(corrected),
        perspective_score=perspective_score,
        single_page_score=single_page_score,
        background_intrusion_ratio=background_intrusion_ratio,
        border_touch_ratio=border_touch_ratio,
        text_density=text_density,
        contour_confidence=contour_confidence,
        gutter_ratio=gutter_ratio,
        opposing_page_ratio=opposing_page_ratio,
        normalized=normalized,
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


def _background_intrusion_ratio(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = _build_fallback_mask(gray)
    if not np.any(mask):
        return 1.0

    inverse = mask == 0
    border = np.zeros_like(mask, dtype=bool)
    border[:12, :] = True
    border[-12:, :] = True
    border[:, :12] = True
    border[:, -12:] = True
    return float(np.mean(inverse & border))


def _text_density(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    return float(np.mean(edges > 0))


def _contour_confidence(
    *,
    page_coverage: float,
    rectangularity: float,
    perspective_score: float,
    border_touch_ratio: float,
) -> float:
    return max(
        0.0,
        min(
            (page_coverage * 0.34)
            + (rectangularity * 0.28)
            + (perspective_score * 0.24)
            + ((1.0 - border_touch_ratio) * 0.14),
            1.0,
        ),
    )


def _gutter_ratio(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    if width < 60:
        return 0.0
    band_half_width = max(int(width * 0.06), 10)
    center = width // 2
    center_band = gray[:, max(center - band_half_width, 0) : min(center + band_half_width, width)]
    left_band = gray[:, : max(int(width * 0.14), 1)]
    right_band = gray[:, width - max(int(width * 0.14), 1) :]
    center_dark = float(np.mean(center_band < 92))
    edge_dark = float((np.mean(left_band < 92) + np.mean(right_band < 92)) / 2.0)
    return max(0.0, center_dark - (edge_dark * 0.55))


def _opposing_page_ratio(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    if width < 60:
        return 0.0

    left_third = gray[:, : width // 3]
    center_third = gray[:, width // 3 : (2 * width) // 3]
    right_third = gray[:, (2 * width) // 3 :]
    left_text = float(np.mean(cv2.Canny(left_third, 60, 160) > 0))
    center_text = float(np.mean(cv2.Canny(center_third, 60, 160) > 0))
    right_text = float(np.mean(cv2.Canny(right_third, 60, 160) > 0))
    side_text = min(left_text, right_text)
    dominant_side = max(left_text, right_text)

    if center_text <= 0.0:
        return dominant_side
    return max(0.0, side_text + max(0.0, dominant_side - (center_text * 0.75)))


def _border_touch_ratio(
    x: int,
    y: int,
    w: int,
    h: int,
    image_width: int,
    image_height: int,
) -> float:
    margin_x = max(int(image_width * 0.04), 8)
    margin_y = max(int(image_height * 0.04), 8)
    touches = 0
    touches += int(x <= margin_x)
    touches += int(y <= margin_y)
    touches += int((x + w) >= image_width - margin_x)
    touches += int((y + h) >= image_height - margin_y)
    return touches / 4.0


def _single_page_shape_score(aspect_ratio: float, border_touch_ratio: float) -> float:
    aspect_penalty = min(abs(aspect_ratio - EXPECTED_PAGE_ASPECT_RATIO) / 0.38, 1.0)
    wide_spread_penalty = max(0.0, (aspect_ratio - 0.92) / 0.35)
    return max(0.0, 1.0 - (aspect_penalty * 0.65) - (wide_spread_penalty * 0.6) - (border_touch_ratio * 0.45))


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
    best_contour = None
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
            best_contour = contour

    if best_contour is None:
        return None

    contour_mask = np.zeros_like(mask)
    cv2.drawContours(contour_mask, [best_contour], -1, 255, thickness=-1)
    coordinates = np.column_stack(np.where(contour_mask > 0))
    if coordinates.size == 0:
        return None

    top, left = coordinates.min(axis=0)
    bottom, right = coordinates.max(axis=0)
    padding = max(6, int(round(min(height, width) * 0.012)))
    left = max(int(left) - padding, 0)
    top = max(int(top) - padding, 0)
    right = min(right + padding + 1, width)
    bottom = min(bottom + padding + 1, height)

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
