from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+asyncpg://receita:receita@localhost:5432/receita"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:5173"]
    anthropic_api_key: str = ""

    max_video_duration_min: int = 60

    whisper_model: str = "small"
    whisper_device: Literal["cpu", "cuda", "auto"] = "cpu"
    whisper_compute_type: str = "int8"
    # Transcrições simultâneas no worker de whisper (cada uma ocupa CPU/RAM inteiras).
    whisper_max_jobs: int = Field(default=1, ge=1, le=4)

    import_job_timeout_s: int = 900
    whisper_job_timeout_s: int = 3600
    import_max_retries: int = 2
    import_retry_delay_s: int = 30
    # Imports parados há mais tempo que isso são dados como falhos pelo worker.
    import_stale_after_min: int = 360


@lru_cache
def get_settings() -> Settings:
    return Settings()
