from functools import lru_cache
from typing import Literal

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
