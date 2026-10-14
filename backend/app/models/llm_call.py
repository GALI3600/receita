import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import CreatedAt, UUIDPrimaryKey, str_enum
from app.models.enums import LLMPurpose

# Códigos só do registro, nunca chegam ao usuário.
# Chamada em andamento: a linha reserva o custo estimado. Se o processo morre, ela fica assim
# e continua contando no orçamento do dia.
LLM_CALL_IN_PROGRESS = "llm_in_progress"
# Chamada interrompida (timeout do job ou do SDK) sem resposta: fica o custo estimado.
LLM_CALL_TIMEOUT = "llm_timeout"


class LLMCall(UUIDPrimaryKey, CreatedAt, Base):
    """Uma linha por chamada ao Claude, gravada antes de chamar (reserva do orçamento) e
    completada no fim.

    É a fonte do custo (orçamento global somado por `created_at`) e do limite de novas
    tentativas quando a geração falha de forma determinística para um vídeo.
    """

    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_created_at", "created_at"),
        Index("ix_llm_calls_started_at", "started_at"),
        Index("ix_llm_calls_video_id_prompt_version", "video_id", "prompt_version"),
    )

    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id"))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(50))
    # Default só no banco (durante o deploy o worker antigo grava sem ele); o código sempre
    # passa o purpose.
    purpose: Mapped[LLMPurpose] = mapped_column(
        str_enum(LLMPurpose, "llm_purpose"), server_default=LLMPurpose.IMPORT.value
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    batch_id: Mapped[str | None] = mapped_column(String(100))
    effort: Mapped[str | None] = mapped_column(String(10))
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    stop_reason: Mapped[str | None] = mapped_column(String(30))
    request_id: Mapped[str | None] = mapped_column(String(100))
    # "5m"/"1h": TTL do marcador de cache no system; nulo = sem marcador.
    cache_marker: Mapped[str | None] = mapped_column(String(2))
    # Custo calculado ao gravar (com as iterations do fallback); na reserva, a estimativa.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
