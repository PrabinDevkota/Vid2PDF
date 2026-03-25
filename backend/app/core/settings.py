from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "Vid2PDF"
    storage_path: str = "backend/data"
    default_sample_fps: float = 4.0
    stable_segment_min_seconds: float = 0.5
    stable_segment_max_change_ratio: float = 0.008
    stable_segment_hash_distance_threshold: int = 3
    stable_segment_mean_diff_threshold: float = 0.012
    dedupe_max_hash_distance: int = 2
    public_artifact_base_url: str = "/artifacts"


settings = Settings()
