"""Registro das chamadas ao Claude em `llm_calls`: reserva antes de chamar, acerto no fim.

A linha nasce `llm_in_progress` com o custo estimado (que já conta no orçamento) e termina com
o usage real, `llm_timeout` (custo estimado) ou apagada quando a API recusou o pedido antes de
processá-lo (erro HTTP, falha ao conectar), que não é cobrado.

Ficam `llm_in_progress`, contando a estimativa no orçamento do dia: um crash do processo, um
segundo cancelamento durante a marcação da interrupção, um cancelamento durante o commit da
própria reserva e uma falha no commit que grava o resultado. O SDK repete timeouts
(`recipe_llm.MAX_RETRIES`), mas a linha reserva uma tentativa só.
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import LLMCall, LLMPurpose, Video
from app.models.llm_call import LLM_CALL_IN_PROGRESS, LLM_CALL_TIMEOUT
from app.services import quotas, recipe_llm

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PendingCall:
    call: LLMCall
    started: float  # time.monotonic() no início, para a latência

    @property
    def latency_ms(self) -> int:
        return round((time.monotonic() - self.started) * 1000)


def reservation_usd(config: recipe_llm.LLMConfig, estimate: recipe_llm.PromptEstimate) -> Decimal:
    """Custo reservado de uma chamada: o prompt estimado (prefixo escrito no cache) e
    min(LLM_RESERVED_OUTPUT_TOKENS, max_tokens) de saída."""
    return quotas.estimate_cost_usd(
        config.model,
        prefix_tokens=estimate.prefix_tokens,
        input_tokens=estimate.input_tokens,
        output_tokens=min(get_settings().llm_reserved_output_tokens, config.max_tokens),
        cache_ttl=config.cache_ttl,
    )


_EMPTY_VIDEO = recipe_llm.VideoContext(
    title="", channel=None, duration_s=0, description="", segments=[], transcript_source=None
)


def minimum_reservation_usd(config: recipe_llm.LLMConfig) -> Decimal:
    """A menor reserva que uma chamada com `config` pode fazer (vídeo sem título nem fala)."""
    return reservation_usd(config, recipe_llm.estimate_prompt(_EMPTY_VIDEO))


async def start(
    session: AsyncSession,
    video: Video,
    *,
    purpose: LLMPurpose,
    config: recipe_llm.LLMConfig,
    estimate: recipe_llm.PromptEstimate,
) -> PendingCall:
    """Reserva o orçamento e grava a chamada; levanta `LLMBudgetExceededError`. Faz commit."""
    call = LLMCall(
        video_id=video.id,
        model=config.model,
        prompt_version=recipe_llm.PROMPT_VERSION,
        usage={},
        error_code=LLM_CALL_IN_PROGRESS,
        purpose=purpose,
        started_at=datetime.now(UTC),
        effort=config.effort,
        max_tokens=config.max_tokens,
        cache_marker=config.cache_ttl,
        cost_usd=reservation_usd(config, estimate),
    )
    await quotas.reserve_llm_call(session, call)
    return PendingCall(call, time.monotonic())


def finish(
    pending: PendingCall,
    *,
    model: str | None,
    usage: dict[str, Any],
    error_code: str | None,
    stop_reason: str | None = None,
    request_id: str | None = None,
) -> None:
    """Grava o resultado de uma chamada paga. Não faz commit (vai junto com a receita)."""
    call = pending.call
    call.model = model or call.model
    call.usage = usage
    call.cost_usd = quotas.llm_cost_usd(call.model, usage, cache_ttl=call.cache_marker)
    call.error_code = error_code
    call.latency_ms = pending.latency_ms
    call.stop_reason = stop_reason
    call.request_id = request_id


def mark_timeout(pending: PendingCall) -> None:
    """Sem resposta, mas talvez cobrada: fica a estimativa. Não faz commit."""
    pending.call.error_code = LLM_CALL_TIMEOUT
    pending.call.latency_ms = pending.latency_ms


async def discard(session: AsyncSession, pending: PendingCall) -> None:
    """Apaga a reserva de uma chamada que a API não processou. Faz commit."""
    await session.delete(pending.call)
    await session.commit()


async def mark_interrupted(session: AsyncSession, pending: PendingCall) -> None:
    """Marca `llm_timeout` depois de uma interrupção sem resultado: cancelamento (prazo do job,
    desligamento do worker) ou exceção inesperada (ex.: o banco caiu no `on_stage`).

    Melhor esforço: se falhar, a linha fica `llm_in_progress`, que também conta no orçamento.
    O rollback descarta uma transação que a interrupção deixou pela metade (os objetos da
    sessão expiram; quem chama recarrega depois de uma exceção, como o `_handle_failure`).
    """
    call_id, latency_ms = pending.call.id, pending.latency_ms  # antes do rollback, que expira
    try:
        await session.rollback()
        await session.execute(
            update(LLMCall)
            .where(LLMCall.id == call_id, LLMCall.error_code == LLM_CALL_IN_PROGRESS)
            .values(error_code=LLM_CALL_TIMEOUT, latency_ms=latency_ms)
        )
        await session.commit()
    except Exception:
        logger.warning("chamada %s: não deu para marcar a interrupção", call_id, exc_info=True)
