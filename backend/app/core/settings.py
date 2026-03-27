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
    quality_min_sharpness_score: float = 0.24
    quality_min_readability_score: float = 0.34
    quality_max_transition_penalty: float = 0.42
    quality_max_occlusion_ratio: float = 0.08
    quality_min_page_coverage: float = 0.42
    quality_min_rectangularity: float = 0.62
    quality_min_single_page_score: float = 0.58
    quality_max_background_intrusion: float = 0.18
    quality_max_border_touch_ratio: float = 0.16
    quality_min_text_density: float = 0.012
    quality_sequence_duplicate_seconds: float = 2.4
    quality_duplicate_content_diff_threshold: float = 0.075
    quality_duplicate_histogram_threshold: float = 0.9
    public_artifact_base_url: str = "/artifacts"


settings = Settings()
