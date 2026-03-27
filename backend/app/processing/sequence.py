from __future__ import annotations

import cv2
import numpy as np

from app.core.settings import settings
from app.processing.types import SelectedPage


def collapse_sequence_candidates(pages: list[SelectedPage]) -> list[SelectedPage]:
    if len(pages) < 2:
        return pages

    ordered_pages = sorted(pages, key=lambda page: page.segment_start)
    collapsed: list[SelectedPage] = []
    cluster: list[SelectedPage] = [ordered_pages[0]]

    for page in ordered_pages[1:]:
        previous = cluster[-1]
        if _belongs_to_cluster(previous, page):
            cluster.append(page)
            continue

        collapsed.append(_pick_cluster_representative(cluster))
        cluster = [page]

    if cluster:
        collapsed.append(_pick_cluster_representative(cluster))

    for index, page in enumerate(collapsed, start=1):
        page.page_number = index
        page.label = f"Page {index}"
        page.page_id = f"page-{index}"

    return collapsed


def _belongs_to_cluster(left: SelectedPage, right: SelectedPage) -> bool:
    temporal_gap = right.segment_start - left.segment_end
    if temporal_gap > settings.quality_sequence_cluster_window_seconds:
        return False

    similarity = _page_similarity(left, right)
    return similarity >= settings.quality_sequence_min_cluster_similarity


def _pick_cluster_representative(cluster: list[SelectedPage]) -> SelectedPage:
    if len(cluster) == 1:
        return cluster[0]

    scored_pages: list[tuple[float, SelectedPage]] = []
    for index, page in enumerate(cluster):
        score = _sequence_rank(page)
        if index > 0:
            score -= _neighbor_penalty(cluster[index - 1], page)
        if index < len(cluster) - 1:
            score -= _neighbor_penalty(page, cluster[index + 1])
        scored_pages.append((score, page))

    return max(scored_pages, key=lambda item: item[0])[1]


def _neighbor_penalty(left: SelectedPage, right: SelectedPage) -> float:
    similarity = _page_similarity(left, right)
    if similarity < settings.quality_sequence_min_cluster_similarity:
        return 0.0

    left_bad = _is_bad_sequence_candidate(left)
    right_bad = _is_bad_sequence_candidate(right)
    if left_bad and right_bad:
        return settings.quality_sequence_bad_neighbor_penalty * 0.35
    if left_bad or right_bad:
        return settings.quality_sequence_bad_neighbor_penalty
    return 0.0


def _is_bad_sequence_candidate(page: SelectedPage) -> bool:
    quality = page.selected_frame.quality
    return (
        quality.rejected
        or quality.transition_penalty > 0.22
        or quality.background_intrusion_ratio > 0.1
        or quality.single_page_score < 0.72
        or quality.page_coverage < 0.6
    )


def _sequence_rank(page: SelectedPage) -> float:
    quality = page.selected_frame.quality
    return (
        quality.score
        + (quality.readability_score * 0.4)
        + (quality.stability_score * 0.25)
        + (quality.single_page_score * 0.22)
        + (quality.page_coverage * 0.18)
        - (quality.transition_penalty * 0.55)
        - (quality.background_intrusion_ratio * 0.35)
        - (0.4 if quality.rejected else 0.0)
    )


def _page_similarity(left: SelectedPage, right: SelectedPage) -> float:
    left_image = _signature_image(left)
    right_image = _signature_image(right)
    correlation = _histogram_similarity(left_image, right_image)
    mean_diff = float(np.mean(np.abs(left_image - right_image)))
    return max(0.0, min((correlation * 0.7) + ((1.0 - min(mean_diff / 0.14, 1.0)) * 0.3), 1.0))


def _signature_image(page: SelectedPage) -> np.ndarray:
    image = page.selected_frame.image
    if image is None:
        return np.zeros((56, 56), dtype=np.float32)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (56, 56), interpolation=cv2.INTER_AREA)
    return cv2.normalize(resized.astype(np.float32), None, 0.0, 1.0, cv2.NORM_MINMAX)


def _histogram_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_hist = cv2.calcHist([np.uint8(left * 255)], [0], None, [32], [0, 256])
    right_hist = cv2.calcHist([np.uint8(right * 255)], [0], None, [32], [0, 256])
    left_hist = cv2.normalize(left_hist, None).flatten()
    right_hist = cv2.normalize(right_hist, None).flatten()
    return float(cv2.compareHist(left_hist, right_hist, cv2.HISTCMP_CORREL))
