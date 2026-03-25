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
    public_artifact_base_url: str = "/artifacts"


settings = Settings()
