from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "Vid2PDF"
    storage_path: str = "backend/data"
    screen_sample_fps: float = 4.0
    screen_stable_segment_min_seconds: float = 0.5
    screen_stable_segment_max_change_ratio: float = 0.008
    screen_stable_segment_hash_distance_threshold: int = 3
    screen_stable_segment_mean_diff_threshold: float = 0.012
    screen_dedupe_max_hash_distance: int = 2
    camera_sample_fps: float = 3.0
    camera_stable_segment_min_seconds: float = 0.6
    camera_stable_segment_max_change_ratio: float = 0.01
    camera_stable_segment_hash_distance_threshold: int = 4
    camera_stable_segment_mean_diff_threshold: float = 0.02
    camera_dedupe_max_hash_distance: int = 3
    quality_min_sharpness_score: float = 0.14
    quality_min_readability_score: float = 0.28
    quality_max_transition_penalty: float = 0.55
    quality_max_occlusion_ratio: float = 0.08
    quality_min_page_coverage: float = 0.42
    quality_min_rectangularity: float = 0.62
    quality_min_single_page_score: float = 0.58
    quality_max_background_intrusion: float = 0.18
    quality_max_border_touch_ratio: float = 0.16
    quality_min_contour_confidence: float = 0.62
    quality_max_gutter_ratio: float = 0.11
    quality_max_opposing_page_ratio: float = 0.2
    quality_min_text_density: float = 0.006
    quality_sequence_duplicate_seconds: float = 4.0
    quality_duplicate_content_diff_threshold: float = 0.06
    quality_duplicate_histogram_threshold: float = 0.9
    quality_sequence_cluster_window_seconds: float = 2.5
    quality_sequence_bad_neighbor_penalty: float = 0.18
    quality_sequence_min_cluster_similarity: float = 0.90
    quality_duplicate_layout_diff_threshold: float = 0.09
    quality_duplicate_profile_diff_threshold: float = 0.08
    quality_duplicate_text_similarity_threshold: float = 0.82
    quality_duplicate_text_structure_threshold: float = 0.82
    quality_duplicate_low_text_visual_threshold: float = 0.94
    quality_duplicate_far_visual_threshold: float = 0.97
    quality_duplicate_near_visual_threshold: float = 0.97
    quality_duplicate_content_match_threshold: float = 0.028
    quality_duplicate_text_density_threshold: float = 0.012
    quality_min_keep_score: float = 0.22
    quality_debug_artifacts_enabled: bool = True
    quality_debug_max_rejected_frames: int = 12
    quality_debug_max_kept_pages: int = 12
    public_artifact_base_url: str = "/artifacts"
    # Absolute paths avoid stale PATH in long-lived uvicorn processes on Windows.
    tesseract_cmd: str | None = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    tectonic_cmd: str = r"C:\Users\prabi\AppData\Local\Programs\tectonic\tectonic.exe"
    ocr_language: str = "eng"
    ocr_min_confidence: float = 35.0
    ocr_soft_confidence: float = 22.0
    ocr_psm: int = 6
    ocr_psm_fallback: int = 4
    ocr_psm_candidates: list[int] = [6, 4, 3]
    ocr_oem: int = 3
    ocr_upscale_min_width: int = 2000
    ocr_preprocess_enabled: bool = True
    ocr_min_plausible_ratio: float = 0.42
    ocr_consecutive_duplicate_similarity: float = 0.85
    ocr_global_duplicate_similarity: float = 0.88


settings = Settings()
