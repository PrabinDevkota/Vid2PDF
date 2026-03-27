from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.settings import settings
from app.processing.deduper import remove_duplicates
from app.processing.document import detect_document_region
from app.processing.pipeline import run_reconstruction_pipeline
from app.processing.scoring import compute_frame_quality
from app.processing.sequence import collapse_sequence_candidates
from app.processing.types import FrameQuality, SampledFrame, SelectedPage

DEFAULT_FIXTURE_MANIFEST = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "quality" / "manifest.json"


@dataclass
class BenchmarkResult:
    name: str
    passed: bool
    detail: str
    skipped: bool = False


@dataclass
class FixtureCase:
    name: str
    input_path: Path
    processing_mode: str
    min_pages: int | None = None
    max_pages: int | None = None
    max_deleted_like_pages: int | None = None
    notes: str | None = None


def main() -> None:
    manifest_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FIXTURE_MANIFEST
    results = [
        benchmark_blur_rejection(),
        benchmark_spread_rejection(),
        benchmark_duplicate_collapse(),
        benchmark_sequence_collapse(),
        *run_fixture_benchmarks(manifest_path),
    ]

    print("Vid2PDF quality benchmark")
    for result in results:
        status = "SKIP" if result.skipped else ("PASS" if result.passed else "FAIL")
        print(f"[{status}] {result.name}: {result.detail}")
    passed_count = sum(result.passed and not result.skipped for result in results)
    executed_count = sum(not result.skipped for result in results)
    print(f"Summary: {passed_count}/{executed_count} executed scenarios passed")


def run_fixture_benchmarks(manifest_path: Path) -> list[BenchmarkResult]:
    if not manifest_path.exists():
        return [BenchmarkResult("fixture_manifest", True, f"{manifest_path} not found; fixture benchmarks skipped.", skipped=True)]

    cases = load_fixture_manifest(manifest_path)
    if not cases:
        return [BenchmarkResult("fixture_manifest", True, "No fixture cases defined.", skipped=True)]

    results: list[BenchmarkResult] = []
    for case in cases:
        if not case.input_path.exists():
            results.append(
                BenchmarkResult(
                    case.name,
                    True,
                    f"Missing media at {case.input_path}; case skipped.",
                    skipped=True,
                )
            )
            continue
        results.append(run_fixture_case(case))
    return results


def load_fixture_manifest(manifest_path: Path) -> list[FixtureCase]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_dir = manifest_path.parent
    cases: list[FixtureCase] = []
    for item in payload.get("cases", []):
        cases.append(
            FixtureCase(
                name=str(item["name"]),
                input_path=(base_dir / str(item["input_path"])).resolve(),
                processing_mode=str(item.get("processing_mode", "camera")),
                min_pages=int(item["min_pages"]) if item.get("min_pages") is not None else None,
                max_pages=int(item["max_pages"]) if item.get("max_pages") is not None else None,
                max_deleted_like_pages=int(item["max_deleted_like_pages"]) if item.get("max_deleted_like_pages") is not None else None,
                notes=str(item["notes"]) if item.get("notes") else None,
            )
        )
    return cases


def run_fixture_case(case: FixtureCase) -> BenchmarkResult:
    original_storage_path = settings.storage_path
    with tempfile.TemporaryDirectory(prefix="vid2pdf-benchmark-") as temp_dir:
        settings.storage_path = temp_dir
        try:
            result = run_reconstruction_pipeline(
                job_id=f"fixture-{case.name}",
                upload_path=str(case.input_path),
                processing_mode=case.processing_mode,
            )
        except Exception as exc:
            return BenchmarkResult(case.name, False, f"Pipeline error: {exc}")
        finally:
            settings.storage_path = original_storage_path

    page_count = len(result.pages)
    weak_pages = sum(1 for page in result.pages if _looks_weak(page))
    failures: list[str] = []
    if case.min_pages is not None and page_count < case.min_pages:
        failures.append(f"pages {page_count} < min {case.min_pages}")
    if case.max_pages is not None and page_count > case.max_pages:
        failures.append(f"pages {page_count} > max {case.max_pages}")
    if case.max_deleted_like_pages is not None and weak_pages > case.max_deleted_like_pages:
        failures.append(f"weak_pages {weak_pages} > max {case.max_deleted_like_pages}")

    detail = f"pages={page_count} weak_pages={weak_pages}"
    if case.notes:
        detail += f" notes={case.notes}"
    if failures:
        detail += " failures=" + ", ".join(failures)
        return BenchmarkResult(case.name, False, detail)
    return BenchmarkResult(case.name, True, detail)


def _looks_weak(page: SelectedPage) -> bool:
    quality = page.selected_frame.quality
    return (
        quality.rejected
        or quality.transition_penalty > 0.2
        or quality.single_page_score < 0.72
        or quality.background_intrusion_ratio > 0.1
        or quality.page_coverage < 0.6
    )


def build_page_image(*, blur: bool = False, darken: int = 0, shift_x: int = 0) -> np.ndarray:
    image = np.full((520, 380, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (40 + shift_x, 32), (322 + shift_x, 470), (242, 242, 242), thickness=-1)
    cv2.rectangle(image, (40 + shift_x, 32), (322 + shift_x, 470), (190, 190, 190), thickness=2)
    for row in range(14):
        y = 62 + (row * 26)
        cv2.line(image, (74 + shift_x, y), (288 + shift_x, y), (35 + darken, 35 + darken, 35 + darken), 2)
    if blur:
        image = cv2.GaussianBlur(image, (13, 13), 4.0)
    return image


def build_alt_page_image() -> np.ndarray:
    image = np.full((520, 380, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (42, 34), (320, 468), (242, 242, 242), thickness=-1)
    cv2.rectangle(image, (42, 34), (320, 468), (190, 190, 190), thickness=2)
    for row in range(7):
        y = 72 + (row * 48)
        cv2.rectangle(image, (78, y), (272, y + 10), (35, 35, 35), thickness=-1)
    cv2.rectangle(image, (82, 392), (236, 420), (35, 35, 35), thickness=-1)
    return image


def build_spread_image() -> np.ndarray:
    image = np.full((540, 760, 3), 244, dtype=np.uint8)
    cv2.rectangle(image, (40, 34), (355, 500), (250, 250, 250), thickness=-1)
    cv2.rectangle(image, (405, 34), (720, 500), (250, 250, 250), thickness=-1)
    cv2.rectangle(image, (367, 34), (393, 500), (40, 40, 40), thickness=-1)
    for row in range(15):
        y = 65 + (row * 26)
        cv2.line(image, (72, y), (318, y), (45, 45, 45), 2)
        cv2.line(image, (438, y), (682, y), (45, 45, 45), 2)
    return image


def benchmark_blur_rejection() -> BenchmarkResult:
    clean = build_page_image()
    blurred = build_page_image(blur=True)
    clean_detection = detect_document_region(clean)
    blurred_detection = detect_document_region(blurred)
    clean_quality = compute_frame_quality(clean, mode="camera", detection=clean_detection, transition_penalty=0.08)
    blurred_quality = compute_frame_quality(blurred, mode="camera", detection=blurred_detection, transition_penalty=0.56)
    passed = (not clean_quality.rejected) and blurred_quality.rejected
    return BenchmarkResult("blur_rejection", passed, f"clean={clean_quality.rejected} blurred={blurred_quality.rejected}")


def benchmark_spread_rejection() -> BenchmarkResult:
    spread = build_spread_image()
    detection = detect_document_region(spread)
    passed = (not detection.normalized) and detection.gutter_ratio > 0.11
    return BenchmarkResult(
        "spread_rejection",
        passed,
        f"normalized={detection.normalized} gutter={detection.gutter_ratio:.3f} single_page={detection.single_page_score:.3f}",
    )


def benchmark_duplicate_collapse() -> BenchmarkResult:
    left = make_selected_page("segment-a", 1.0, build_page_image(), 0.82)
    right = make_selected_page("segment-b", 2.2, build_page_image(darken=10, shift_x=4), 0.95)
    alt = make_selected_page("segment-c", 4.0, build_alt_page_image(), 0.88)
    deduped = remove_duplicates([left, right, alt], max_hamming_distance=6)
    passed = len(deduped) == 2
    return BenchmarkResult("duplicate_collapse", passed, f"kept={len(deduped)}")


def benchmark_sequence_collapse() -> BenchmarkResult:
    cluster = [
        make_selected_page("segment-a", 1.0, build_page_image(), 0.78, transition_penalty=0.16),
        make_selected_page("segment-b", 1.45, build_page_image(darken=3), 0.94, transition_penalty=0.03),
        make_selected_page("segment-c", 1.95, build_page_image(shift_x=2), 0.8, transition_penalty=0.17),
    ]
    collapsed = collapse_sequence_candidates(cluster)
    passed = len(collapsed) == 1 and collapsed[0].source_segment_id == "segment-b"
    return BenchmarkResult("sequence_collapse", passed, f"kept={len(collapsed)} winner={collapsed[0].source_segment_id}")


def make_selected_page(
    source_segment_id: str,
    start_time: float,
    image: np.ndarray,
    score: float,
    *,
    transition_penalty: float = 0.02,
) -> SelectedPage:
    quality = FrameQuality(
        sharpness=2200.0,
        brightness=180.0,
        contrast=66.0,
        edge_density=0.04,
        page_coverage=0.82,
        rectangularity=0.92,
        occlusion_ratio=0.0,
        transition_penalty=transition_penalty,
        readability_score=0.88,
        sharpness_score=0.9,
        contrast_score=0.85,
        brightness_score=0.92,
        text_density=0.028,
        single_page_score=0.95,
        background_intrusion_ratio=0.02,
        border_touch_ratio=0.02,
        contour_confidence=0.94,
        gutter_ratio=0.01,
        opposing_page_ratio=0.03,
        stability_score=0.95,
        rejected=False,
        rejection_reasons=[],
        score=score,
        perceptual_hash="0f0f0f0f0f0f0f0f",
    )
    sampled = SampledFrame(
        timestamp=start_time + 0.2,
        frame_index=int(start_time * 10),
        image=image,
        quality=quality,
        change_ratio=0.02,
    )
    return SelectedPage(
        page_id=f"{source_segment_id}-page",
        page_number=1,
        label=source_segment_id,
        source_segment_id=source_segment_id,
        segment_start=start_time,
        segment_end=start_time + 0.4,
        selected_frame=sampled,
        image_path="",
        thumbnail_path="",
    )


if __name__ == "__main__":
    main()
