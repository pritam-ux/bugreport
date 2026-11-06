from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    environment: str = "development"
    mongodb_uri: str = "mongodb://localhost:27018"
    mongodb_db: str = "bugsense_ai"

    cors_origins: str = "http://localhost:5180,http://127.0.0.1:5180"

    embedding_model: str = "all-MiniLM-L6-v2"  # a folder in backend/models
    artifacts_dir: Path = BACKEND_DIR / "artifacts"
    # Below Vercel's 4.5 MB request limit, leaving room for multipart overhead.
    max_upload_mb: int = 4

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
