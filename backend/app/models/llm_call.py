import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import CreatedAt, UUIDPrimaryKey


class LLMCall(UUIDPrimaryKey, CreatedAt, Base):
    """Registro só de inserção de cada chamada paga ao Claude, com sucesso ou não.

    É a fonte do custo (orçamento global somado por `created_at`) e do limite de novas
    tentativas quando a geração falha de forma determinística para um vídeo.
    """

    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_created_at", "created_at"),
        Index("ix_llm_calls_video_id_prompt_version", "video_id", "prompt_version"),
    )

    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id"))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(50))
