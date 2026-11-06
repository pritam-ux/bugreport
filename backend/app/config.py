from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    environment: str = "development"
    mongodb_uri: str = "mongodb://localhost:27018"
    mongodb_db: str = "bugsense_ai"

    # Required, with no default: a shared fallback would let anyone forge tokens.
    jwt_secret: str
    jwt_expires_minutes: int = 480

    cors_origins: str = "http://localhost:5180,http://127.0.0.1:5180"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    artifacts_dir: Path = BACKEND_DIR / "artifacts"
    upload_dir: Path = BACKEND_DIR / "uploads"
    max_upload_mb: int = 10

    # No mail service is configured. In development the reset link is returned
    # by the API so the flow can be used. Production never exposes it.
    expose_reset_token: bool = True

    @field_validator("jwt_secret")
    @classmethod
    def secret_is_strong(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters. See backend/.env.example.")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def reset_token_visible(self) -> bool:
        return self.expose_reset_token and self.environment != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
