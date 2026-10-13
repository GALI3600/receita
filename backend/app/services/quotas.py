"""Limites de uso: cota diária de receitas novas por usuário e orçamento diário do Claude.

Todos contam por dia UTC. A cota soma os imports concluídos hoje que geraram receita nova com
o Claude (`Import.charged_at`) e os que ainda estão em andamento ou adiados, que podem vir a
gastar: assim vários imports simultâneos não passam juntos do limite. Falhas não gastam a cota,
mas as que custaram uma chamada ao Claude ou uma execução do whisper (`Import.cost_incurred_at`)
têm um limite diário próprio, para que vídeos que não são receita não esgotem o orçamento de
todos. O orçamento soma o custo de cada chamada paga ao Claude gravada em `llm_calls`, calculado
a partir do `usage`.
"""

import logging
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import LLMBudgetExceededError, QuotaExceededError, TooManyFailedImportsError
from app.models import UNFINISHED_IMPORT_STATUSES, Import, ImportStatus, LLMCall

logger = logging.getLogger(__name__)

_MTOK = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """US$ por milhão de tokens."""

    input: Decimal
    output: Decimal
    cache_read: Decimal

    @property
    def cache_write_5m(self) -> Decimal:
        return self.input * Decimal("1.25")

    @property
    def cache_write_1h(self) -> Decimal:
        return self.input * 2


# Escrita no cache: 1,25× a entrada (TTL de 5 min, o usado aqui) ou 2× (TTL de 1 h). Os modelos
# além do claude-opus-5-5 só aparecem quando o fallback do servidor responde no lugar dele.
MODEL_PRICES: dict[str, ModelPrice] = {
    "claude-opus-5-5": ModelPrice(Decimal(4), Decimal(20), Decimal("0.20")),
    "claude-opus-5": ModelPrice(Decimal(5), Decimal(25), Decimal("0.50")),
    "claude-opus-4-8": ModelPrice(Decimal(5), Decimal(25), Decimal("0.50")),
}
# Modelo sem preço cadastrado: cobra pelo mais caro, para o orçamento errar para o lado seguro.
_FALLBACK_PRICE = max(MODEL_PRICES.values(), key=lambda price: price.output)


# --- Dia UTC ----------------------------------------------------------------------------------


def day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def next_day_start(now: datetime | None = None) -> datetime:
    return day_start(now) + timedelta(days=1)


def seconds_until_tomorrow(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    return int((next_day_start(now) - now).total_seconds())


# --- Cota por usuário -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImportQuota:
    used: int
    limit: int
    resets_at: datetime

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


@dataclass(frozen=True, slots=True)
class _ImportsToday:
    charged: int
    unfinished: int
    costly_failures: int


async def _imports_today(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> _ImportsToday:
    today = day_start(now)
    charged, unfinished, costly_failures = (
        await session.execute(
            select(
                func.count().filter(Import.charged_at >= today),
                func.count().filter(Import.status.in_(list(UNFINISHED_IMPORT_STATUSES))),
                func.count().filter(
                    Import.status == ImportStatus.FAILED, Import.cost_incurred_at >= today
                ),
            ).where(Import.user_id == user_id)
        )
    ).one()
    return _ImportsToday(charged, unfinished, costly_failures)


def _quota(usage: _ImportsToday, now: datetime) -> ImportQuota:
    return ImportQuota(
        used=usage.charged + usage.unfinished,
        limit=get_settings().daily_import_limit,
        resets_at=next_day_start(now),
    )


async def import_quota(
    session: AsyncSession, user_id: uuid.UUID, now: datetime | None = None
) -> ImportQuota:
    """Uso do dia: receitas novas concluídas hoje + imports em andamento ou adiados."""
    now = now or datetime.now(UTC)
    return _quota(await _imports_today(session, user_id, now), now)


async def ensure_import_quota(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Levanta `QuotaExceededError` se o usuário não pode começar outra receita nova hoje.

    Levanta `TooManyFailedImportsError` se ele já chegou a `DAILY_FAILED_IMPORT_LIMIT` falhas
    caras hoje. Para valer com pedidos simultâneos, quem chama precisa ter travado o usuário na
    transação (ver `imports.create_import`) e gravar o import novo antes do commit.
    """
    now = datetime.now(UTC)
    usage = await _imports_today(session, user_id, now)
    quota = _quota(usage, now)
    if quota.remaining <= 0:
        raise QuotaExceededError(
            seconds_until_tomorrow(now), detail=f"{quota.used}/{quota.limit} hoje"
        )
    failure_limit = get_settings().daily_failed_import_limit
    if usage.costly_failures >= failure_limit:
        raise TooManyFailedImportsError(
            seconds_until_tomorrow(now),
            detail=f"{usage.costly_failures}/{failure_limit} falhas caras hoje",
        )


# --- Orçamento do Claude ----------------------------------------------------------------------


def _tokens(usage: dict[str, Any], name: str) -> int:
    value = usage.get(name)
    return value if isinstance(value, int) and value > 0 else 0


def _attempt_cost(model: str, usage: dict[str, Any]) -> Decimal:
    price = MODEL_PRICES.get(model)
    if price is None:
        logger.warning("modelo %s sem preço cadastrado; usando o mais caro", model)
        price = _FALLBACK_PRICE

    cache_write = _tokens(usage, "cache_creation_input_tokens")
    breakdown = usage.get("cache_creation")
    write_1h = _tokens(breakdown, "ephemeral_1h_input_tokens") if isinstance(breakdown, dict) else 0
    write_5m = max(0, cache_write - write_1h)

    total = (
        _tokens(usage, "input_tokens") * price.input
        + _tokens(usage, "output_tokens") * price.output
        + _tokens(usage, "cache_read_input_tokens") * price.cache_read
        + write_5m * price.cache_write_5m
        + write_1h * price.cache_write_1h
    )
    return total / _MTOK


def llm_cost_usd(model: str, usage: dict[str, Any]) -> Decimal:
    """Custo em US$ de uma chamada ao Claude a partir do `usage` gravado.

    Com o fallback do servidor, `usage.iterations` traz cada tentativa (a recusada e a do
    modelo que respondeu) e o `usage` do topo só a última: aí a soma é das tentativas, cada uma
    pelo preço do seu modelo. Uma tentativa sem `model` é cobrada pelo modelo da resposta.
    """
    iterations = usage.get("iterations")
    if isinstance(iterations, list) and iterations:
        return sum(
            (
                _attempt_cost(str(entry.get("model") or model), entry)
                for entry in iterations
                if isinstance(entry, dict)
            ),
            Decimal(0),
        )
    return _attempt_cost(model, usage)


async def llm_spend_today(session: AsyncSession, now: datetime | None = None) -> Decimal:
    rows = await session.execute(
        select(LLMCall.model, LLMCall.usage).where(LLMCall.created_at >= day_start(now))
    )
    return sum((llm_cost_usd(model, usage) for model, usage in rows), Decimal(0))


@dataclass(frozen=True, slots=True)
class DailySpend:
    day: date
    calls: int
    failed_calls: int
    cost_usd: Decimal


async def llm_spend_by_day(
    session: AsyncSession, days: int, now: datetime | None = None
) -> list[DailySpend]:
    """Gasto com o Claude nos últimos `days` dias UTC (hoje incluído), do mais recente ao mais
    antigo; dias sem chamadas aparecem zerados. É o que `python -m app.cli llm-spend` mostra."""
    today = day_start(now)
    since = today - timedelta(days=days - 1)
    rows = await session.execute(
        select(LLMCall.created_at, LLMCall.model, LLMCall.usage, LLMCall.error_code).where(
            LLMCall.created_at >= since
        )
    )
    days_back = [(today - timedelta(days=offset)).date() for offset in range(days)]
    by_day = {day: DailySpend(day, 0, 0, Decimal(0)) for day in days_back}
    for created_at, model, usage, error_code in rows:
        spend = by_day[created_at.astimezone(UTC).date()]
        by_day[spend.day] = replace(
            spend,
            calls=spend.calls + 1,
            failed_calls=spend.failed_calls + (error_code is not None),
            cost_usd=spend.cost_usd + llm_cost_usd(model, usage),
        )
    return list(by_day.values())


async def ensure_llm_budget(session: AsyncSession) -> None:
    """Levanta `LLMBudgetExceededError` se o gasto de hoje já chegou a `DAILY_LLM_BUDGET_USD`.

    A checagem vem antes de cada chamada; chamadas que já estavam em voo quando o teto foi
    atingido ainda terminam, então o gasto pode passar um pouco do teto.
    """
    spent = await llm_spend_today(session)
    await session.commit()
    budget = Decimal(str(get_settings().daily_llm_budget_usd))
    if spent >= budget:
        raise LLMBudgetExceededError(detail=f"gasto de hoje US$ {spent:.4f} >= US$ {budget}")


async def llm_budget_available(session: AsyncSession) -> bool:
    try:
        await ensure_llm_budget(session)
    except LLMBudgetExceededError:
        return False
    return True
