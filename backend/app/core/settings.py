from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "Vid2PDF"
    storage_path: str = "backend/data"
    default_sample_fps: float = 2.0
    stable_segment_min_seconds: float = 0.9
    stable_segment_max_change_ratio: float = 0.045
    public_artifact_base_url: str = "http://localhost:8000/artifacts"


settings = Settings()
