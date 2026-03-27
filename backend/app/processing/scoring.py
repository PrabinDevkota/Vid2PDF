from __future__ import annotations

import cv2
import numpy as np

from app.core.settings import settings
from app.processing.types import DocumentDetection, FrameQuality, ProcessingMode


def compute_frame_quality(
    frame: np.ndarray,
    mode: ProcessingMode,
    detection: DocumentDetection | None = None,
    transition_penalty: float = 0.0,
) -> FrameQuality:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    edges = cv2.Canny(gray, 80, 180)
    edge_density = float(np.mean(edges > 0))
    brightness_score = max(0.0, 1.0 - abs(brightness - 178.0) / 178.0)
    contrast_score = min(contrast / 72.0, 1.0)
    sharpness_score = min(sharpness / 1800.0, 1.0)
    edge_score = min(edge_density / 0.18, 1.0)
    readability_score = (contrast_score * 0.4) + (edge_score * 0.35) + (sharpness_score * 0.25)
    page_coverage = detection.page_coverage if detection else 1.0
    rectangularity = detection.rectangularity if detection else 1.0
    occlusion_ratio = detection.occlusion_ratio if detection else 0.0
    single_page_score = detection.single_page_score if detection else 1.0
    background_intrusion_ratio = detection.background_intrusion_ratio if detection else 0.0
    border_touch_ratio = detection.border_touch_ratio if detection else 0.0
    text_density = detection.text_density if detection else edge_density
    perspective_score = detection.perspective_score if detection else 1.0
    stability_score = max(0.0, 1.0 - min(transition_penalty, 1.0))
    rejection_reasons: list[str] = []

    if sharpness_score < settings.quality_min_sharpness_score:
        rejection_reasons.append("severe_defocus")
    if readability_score < settings.quality_min_readability_score:
        rejection_reasons.append("low_readability")
    if transition_penalty > settings.quality_max_transition_penalty:
        rejection_reasons.append("transition_motion")
    if text_density < settings.quality_min_text_density:
        rejection_reasons.append("insufficient_text_detail")

    if mode == "camera":
        if detection is None or not detection.found:
            rejection_reasons.append("no_page_detected")
        else:
            if page_coverage < settings.quality_min_page_coverage:
                rejection_reasons.append("partial_page_visibility")
            if rectangularity < settings.quality_min_rectangularity:
                rejection_reasons.append("incomplete_page_contour")
            if single_page_score < settings.quality_min_single_page_score:
                rejection_reasons.append("spread_or_off_axis_page")
            if occlusion_ratio > settings.quality_max_occlusion_ratio:
                rejection_reasons.append("occlusion_or_finger")
            if background_intrusion_ratio > settings.quality_max_background_intrusion:
                rejection_reasons.append("background_clutter")
            if border_touch_ratio > settings.quality_max_border_touch_ratio:
                rejection_reasons.append("page_touches_frame_border")
            if not detection.normalized:
                rejection_reasons.append("unstable_normalization")

        score = (
            (readability_score * 0.22)
            + (sharpness_score * 0.12)
            + (contrast_score * 0.07)
            + (brightness_score * 0.04)
            + (text_density * 9.0)
            + (page_coverage * 0.16)
            + (rectangularity * 0.1)
            + (single_page_score * 0.12)
            + (perspective_score * 0.06)
            + (stability_score * 0.11)
            - (occlusion_ratio * 0.28)
            - (background_intrusion_ratio * 0.26)
            - (border_touch_ratio * 0.18)
            - (transition_penalty * 0.5)
        )
    else:
        score = (
            (readability_score * 0.34)
            + (sharpness_score * 0.24)
            + (contrast_score * 0.14)
            + (brightness_score * 0.08)
            + (text_density * 7.5)
            + (stability_score * 0.2)
            - (transition_penalty * 0.45)
        )

    rejected = len(rejection_reasons) > 0
    if rejected:
        score -= min(len(rejection_reasons) * 0.24, 1.2)

    return FrameQuality(
        sharpness=sharpness,
        brightness=brightness,
        contrast=contrast,
        edge_density=edge_density,
        page_coverage=page_coverage,
        rectangularity=rectangularity,
        occlusion_ratio=occlusion_ratio,
        transition_penalty=transition_penalty,
        readability_score=readability_score,
        sharpness_score=sharpness_score,
        contrast_score=contrast_score,
        brightness_score=brightness_score,
        text_density=text_density,
        single_page_score=single_page_score,
        background_intrusion_ratio=background_intrusion_ratio,
        border_touch_ratio=border_touch_ratio,
        stability_score=stability_score,
        rejected=rejected,
        rejection_reasons=rejection_reasons,
        score=score,
        perceptual_hash=_difference_hash(gray),
    )


def _difference_hash(gray: np.ndarray, hash_size: int = 8) -> str:
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    bits = "".join("1" if value else "0" for value in diff.flatten())
    return f"{int(bits, 2):0{hash_size * hash_size // 4}x}"
