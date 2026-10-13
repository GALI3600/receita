from typing import Any

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import CreatedAt, UUIDPrimaryKey, str_enum
from app.schemas.transcript import Segment, TranscriptSource


class Video(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "videos"

    youtube_id: Mapped[str] = mapped_column(String(11), unique=True)
    title: Mapped[str] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(String(255))
    duration_s: Mapped[int] = mapped_column(Integer)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    embeddable: Mapped[bool] = mapped_column(Boolean)

    transcript: Mapped[list[Segment] | None] = mapped_column(JSONB)
    transcript_source: Mapped[TranscriptSource | None] = mapped_column(
        str_enum(TranscriptSource, "transcript_source")
    )

    generated_recipe: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    llm_model: Mapped[str | None] = mapped_column(String(100))
    llm_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    prompt_version: Mapped[str | None] = mapped_column(String(50))
