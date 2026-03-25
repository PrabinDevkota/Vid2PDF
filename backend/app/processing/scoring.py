from __future__ import annotations

import cv2
import numpy as np

from app.processing.types import FrameQuality


def compute_frame_quality(frame: np.ndarray) -> FrameQuality:
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
        score=score,
        perceptual_hash=_difference_hash(gray),
    )


def _difference_hash(gray: np.ndarray, hash_size: int = 8) -> str:
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    bits = "".join("1" if value else "0" for value in diff.flatten())
    return f"{int(bits, 2):0{hash_size * hash_size // 4}x}"
