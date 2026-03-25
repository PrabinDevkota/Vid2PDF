from __future__ import annotations

import cv2
import numpy as np

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

    if mode == "camera":
        score = (
            (sharpness_score * 0.18)
            + (brightness_score * 0.08)
            + (contrast_score * 0.14)
            + (edge_score * 0.12)
            + (page_coverage * 0.2)
            + (rectangularity * 0.12)
            + ((detection.perspective_score if detection else 0.0) * 0.08)
            + (readability_score * 0.18)
            - (occlusion_ratio * 0.18)
            - (transition_penalty * 0.28)
        )
    else:
        score = (
            (sharpness_score * 0.45)
            + (contrast_score * 0.2)
            + (brightness_score * 0.2)
            + (edge_score * 0.15)
        )

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
        score=score,
        perceptual_hash=_difference_hash(gray),
    )


def _difference_hash(gray: np.ndarray, hash_size: int = 8) -> str:
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    bits = "".join("1" if value else "0" for value in diff.flatten())
    return f"{int(bits, 2):0{hash_size * hash_size // 4}x}"
