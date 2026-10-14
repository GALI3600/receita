"""Limites de uso: cota diária de receitas novas por usuário e orçamento diário do Claude.

Todos contam por dia UTC. A cota soma os imports concluídos hoje que geraram receita nova com
o Claude (`Import.charged_at`) e os que ainda estão em andamento ou adiados, que podem vir a
gastar: assim vários imports simultâneos não passam juntos do limite. Falhas não gastam a cota,
mas as que custaram uma chamada ao Claude ou uma execução do whisper (`Import.cost_incurred_at`)
têm um limite diário próprio, para que vídeos que não são receita não esgotem o orçamento de
todos. O orçamento soma o `cost_usd` de cada chamada ao Claude gravada em `llm_calls` (a
estimativa enquanto a chamada está em andamento; nas linhas anteriores à coluna, o custo
calculado do `usage`). Há dois tetos diários: o de produção (`DAILY_LLM_BUDGET_USD`) e o do
eval (`EVAL_DAILY_LLM_BUDGET_USD`), cada um somando só as chamadas do seu `purpose`.
"""

import logging
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import LLMBudgetExceededError, QuotaExceededError, TooManyFailedImportsError
from app.models import UNFINISHED_IMPORT_STATUSES, Import, ImportStatus, LLMCall, LLMPurpose
from app.models.llm_call import LLM_CALL_IN_PROGRESS, LLM_CALL_TIMEOUT

logger = logging.getLogger(__name__)

_MTOK = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """US$ por milhão de tokens. A leitura do cache tem preço próprio por modelo."""

    input: Decimal
    output: Decimal
    cache_read: Decimal
    # Prompt longo (só Haiku 5.5): acima de `long_prompt_above` tokens de prompt (entrada +
    # leitura + escrita no cache), a requisição inteira, saída inclusive, usa `long_prompt`.
    long_prompt: "ModelPrice | None" = None
    long_prompt_above: int = 0

    @property
    def cache_write_5m(self) -> Decimal:
        return self.input * Decimal("1.25")

    @property
    def cache_write_1h(self) -> Decimal:
        return self.input * 2


def _price(input: str, output: str, cache_read: str, **kwargs: Any) -> ModelPrice:
    return ModelPrice(Decimal(input), Decimal(output), Decimal(cache_read), **kwargs)


# Lista de preços de 2026-10-14. Escrita no cache: 1,25× a entrada (TTL de 5 min) ou 2× (TTL de
# 1 h). Além do modelo configurado, aparecem os que o fallback do servidor usa no lugar dele e
# os que o eval testa.
MODEL_PRICES: dict[str, ModelPrice] = {
    "claude-fable-5-1": _price("10", "50", "0.25"),
    "claude-opus-5-5": _price("4", "20", "0.20"),
    "claude-opus-5": _price("5", "25", "0.50"),
    "claude-opus-4-8": _price("5", "25", "0.50"),
    "claude-sonnet-5-5": _price("2", "10", "0.10"),
    "claude-sonnet-5": _price("2", "10", "0.20"),
    "claude-haiku-5-5": _price(
        "0.10",
        "0.50",
        "0.01",
        long_prompt=_price("0.50", "2.50", "0.05"),
        long_prompt_above=100_000,
    ),
    "claude-haiku-4-5": _price("1", "5", "0.10"),
}


def _highest_price(prices: list[ModelPrice]) -> ModelPrice:
    tiers = prices + [p.long_prompt for p in prices if p.long_prompt is not None]
    return ModelPrice(
        input=max(p.input for p in tiers),
        output=max(p.output for p in tiers),
        cache_read=max(p.cache_read for p in tiers),
    )


# Modelo sem preço cadastrado (o roteamento do fallback não é publicado): o maior preço
# publicado em cada categoria, para o orçamento errar para o lado seguro. O Fable 5 (legado)
# cai aqui sem preço conferido.
_UNKNOWN_MODEL_PRICE = _highest_price(list(MODEL_PRICES.values()))
BATCH_MULTIPLIER = Decimal("0.5")  # usage.service_tier == "batch"
US_GEO_MULTIPLIER = Decimal("1.1")  # usage.inference_geo == "us"


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


def _attempt_cost(
    model: str,
    usage: dict[str, Any],
    *,
    service_tier: Any = None,
    inference_geo: Any = None,
    cache_creation: Any = None,
    cache_ttl: str | None = None,
) -> Decimal:
    """Custo de uma tentativa; os campos nomeados vêm do topo do `usage` e valem quando a
    tentativa não traz os seus."""
    price = MODEL_PRICES.get(model)
    if price is None:
        logger.warning("modelo %s sem preço cadastrado; usando o maior preço publicado", model)
        price = _UNKNOWN_MODEL_PRICE

    cache_write = _tokens(usage, "cache_creation_input_tokens")
    cache_read = _tokens(usage, "cache_read_input_tokens")
    input_tokens = _tokens(usage, "input_tokens")
    if price.long_prompt and input_tokens + cache_read + cache_write > price.long_prompt_above:
        price = price.long_prompt

    breakdown = usage.get("cache_creation")
    if isinstance(breakdown, dict):
        write_1h = _tokens(breakdown, "ephemeral_1h_input_tokens")
    elif cache_ttl is not None:
        # As iterations do fallback trazem só o total da escrita. A requisição tem um único
        # marcador de cache, então o TTL dele vale para todas as tentativas.
        write_1h = cache_write if cache_ttl == "1h" else 0
    else:
        # Sem o marcador (linhas antigas, receita gravada): o TTL do que o topo escreveu. Se a
        # última tentativa não escreveu nada, a escrita das anteriores conta como 5 min.
        top_1h = (
            _tokens(cache_creation, "ephemeral_1h_input_tokens")
            if isinstance(cache_creation, dict)
            else 0
        )
        write_1h = cache_write if top_1h else 0
    write_5m = max(0, cache_write - write_1h)

    total = (
        input_tokens * price.input
        + _tokens(usage, "output_tokens") * price.output
        + cache_read * price.cache_read
        + write_5m * price.cache_write_5m
        + write_1h * price.cache_write_1h
    )
    if usage.get("service_tier", service_tier) == "batch":
        total *= BATCH_MULTIPLIER
    if usage.get("inference_geo", inference_geo) == "us":
        total *= US_GEO_MULTIPLIER
    return total / _MTOK


def llm_cost_usd(model: str, usage: dict[str, Any], *, cache_ttl: str | None = None) -> Decimal:
    """Custo em US$ de uma chamada ao Claude a partir do `usage` gravado.

    Com o fallback do servidor, `usage.iterations` traz cada tentativa (a recusada e a do
    modelo que respondeu) e o `usage` do topo só a última: aí a soma é das tentativas, cada uma
    pelo preço do seu modelo. Uma tentativa sem `model` é cobrada pelo modelo da resposta. Batch
    (metade do preço) e `inference_geo` "us" (1,1×) vêm do topo, se a tentativa não os traz.
    Recusas em categorias que a API não cobra entram mesmo assim: as iterations não trazem a
    categoria (erra para o lado seguro). `cache_ttl` é o marcador de cache da requisição: dá o
    TTL da escrita das tentativas sem `cache_creation` (sem ele, vale o TTL escrito no topo).
    """
    top = {
        "service_tier": usage.get("service_tier"),
        "inference_geo": usage.get("inference_geo"),
        "cache_creation": usage.get("cache_creation"),
        "cache_ttl": cache_ttl,
    }
    iterations = usage.get("iterations")
    if isinstance(iterations, list) and iterations:
        return sum(
            (
                _attempt_cost(str(entry.get("model") or model), entry, **top)
                for entry in iterations
                if isinstance(entry, dict)
            ),
            Decimal(0),
        )
    return _attempt_cost(model, usage, **top)


def estimate_cost_usd(
    model: str,
    *,
    prefix_tokens: int,
    input_tokens: int,
    output_tokens: int,
    cache_ttl: str | None,
    cache_hit: bool = False,
) -> Decimal:
    """Custo esperado de uma chamada síncrona: o prefixo pago como escrita no cache (o pior
    caso; como leitura com `cache_hit`), a mensagem como entrada e `output_tokens` de saída."""
    cached = cache_ttl is not None
    write = prefix_tokens if cached and not cache_hit else 0
    usage = {
        "input_tokens": input_tokens + (0 if cached else prefix_tokens),
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": write,
        "cache_read_input_tokens": prefix_tokens if cached and cache_hit else 0,
        "cache_creation": {"ephemeral_1h_input_tokens": write if cache_ttl == "1h" else 0},
    }
    return llm_cost_usd(model, usage)


def row_cost(model: str, usage: dict[str, Any], cost_usd: Decimal | None) -> Decimal:
    """Custo de uma linha de `llm_calls`; as anteriores à coluna `cost_usd` são calculadas do
    usage."""
    return cost_usd if cost_usd is not None else llm_cost_usd(model, usage)


class Budget(StrEnum):
    PRODUCTION = "production"
    EVAL = "eval"


def budget_for(purpose: LLMPurpose) -> Budget:
    return Budget.EVAL if purpose == LLMPurpose.EVAL else Budget.PRODUCTION


def budget_limit_usd(budget: Budget) -> Decimal:
    settings = get_settings()
    if budget is Budget.EVAL:
        return Decimal(str(settings.eval_daily_llm_budget_usd))
    return Decimal(str(settings.daily_llm_budget_usd))


def _in_budget(budget: Budget) -> ColumnElement[bool]:
    if budget is Budget.EVAL:
        return LLMCall.purpose == LLMPurpose.EVAL
    return LLMCall.purpose != LLMPurpose.EVAL


async def llm_spend_today(
    session: AsyncSession, budget: Budget = Budget.PRODUCTION, now: datetime | None = None
) -> Decimal:
    rows = await session.execute(
        select(LLMCall.model, LLMCall.usage, LLMCall.cost_usd).where(
            LLMCall.created_at >= day_start(now), _in_budget(budget)
        )
    )
    return sum((row_cost(*row) for row in rows), Decimal(0))


@dataclass(frozen=True, slots=True)
class DailySpend:
    day: date
    # As contagens somam todos os purposes; só o custo é separado entre produção e eval.
    calls: int
    failed_calls: int
    # Sem resposta: em andamento ou interrompidas (contam com o custo estimado).
    unfinished_calls: int
    cost_usd: Decimal
    eval_cost_usd: Decimal


async def llm_spend_by_day(
    session: AsyncSession, days: int, now: datetime | None = None
) -> list[DailySpend]:
    """Gasto com o Claude nos últimos `days` dias UTC (hoje incluído), do mais recente ao mais
    antigo; dias sem chamadas aparecem zerados. É o que `python -m app.cli llm-spend` mostra."""
    today = day_start(now)
    since = today - timedelta(days=days - 1)
    rows = await session.execute(
        select(
            LLMCall.created_at,
            LLMCall.model,
            LLMCall.usage,
            LLMCall.cost_usd,
            LLMCall.error_code,
            LLMCall.purpose,
        ).where(LLMCall.created_at >= since)
    )
    days_back = [(today - timedelta(days=offset)).date() for offset in range(days)]
    zero = Decimal(0)
    by_day = {day: DailySpend(day, 0, 0, 0, zero, zero) for day in days_back}
    for created_at, model, usage, cost_usd, error_code, purpose in rows:
        spend = by_day[created_at.astimezone(UTC).date()]
        cost = row_cost(model, usage, cost_usd)
        is_eval = budget_for(purpose) is Budget.EVAL
        by_day[spend.day] = replace(
            spend,
            calls=spend.calls + 1,
            # Uma chamada em voo ainda não falhou; a interrompida falhou e também fica sem resposta.
            failed_calls=spend.failed_calls
            + (error_code is not None and error_code != LLM_CALL_IN_PROGRESS),
            unfinished_calls=spend.unfinished_calls
            + (error_code in (LLM_CALL_IN_PROGRESS, LLM_CALL_TIMEOUT)),
            cost_usd=spend.cost_usd + (zero if is_eval else cost),
            eval_cost_usd=spend.eval_cost_usd + (cost if is_eval else zero),
        )
    return list(by_day.values())


async def _check_budget(session: AsyncSession, budget: Budget, extra_usd: Decimal) -> None:
    """Levanta `LLMBudgetExceededError` se o gasto de hoje mais `extra_usd` passa do teto. Não
    faz commit."""
    spent = await llm_spend_today(session, budget)
    limit = budget_limit_usd(budget)
    if spent >= limit or spent + extra_usd > limit:
        raise LLMBudgetExceededError(
            detail=f"{budget}: gasto de hoje US$ {spent:.4f} + US$ {extra_usd:.4f} > US$ {limit}"
        )


async def ensure_llm_budget(
    session: AsyncSession, budget: Budget = Budget.PRODUCTION, extra_usd: Decimal = Decimal(0)
) -> None:
    """Levanta `LLMBudgetExceededError` se o gasto de hoje já chegou ao teto de `budget` ou não
    deixa folga para `extra_usd`.

    O gasto inclui as reservas das chamadas em andamento; quem vai chamar o Claude usa
    `reserve_llm_call`, que também confere a estimativa da chamada nova.
    """
    try:
        await _check_budget(session, budget, extra_usd)
    finally:
        await session.commit()


async def llm_budget_available(session: AsyncSession, extra_usd: Decimal = Decimal(0)) -> bool:
    try:
        await ensure_llm_budget(session, extra_usd=extra_usd)
    except LLMBudgetExceededError:
        return False
    return True


# Chave do advisory lock que serializa "conferir orçamento + gravar a reserva" entre processos.
_BUDGET_LOCK_KEY = 0x6C6C6D62  # "llmb"


async def reserve_llm_call(session: AsyncSession, call: LLMCall) -> None:
    """Grava a chamada `call` (com `cost_usd` = estimativa) se cabe no orçamento do purpose dela.

    Levanta `LLMBudgetExceededError` sem gravar nada. Conferência e insert ficam na mesma
    transação, sob um advisory lock: dois jobs não reservam juntos a última folga do dia. A
    sessão não pode ter mudanças pendentes (o pipeline sempre comita antes): o commit da
    reserva as levaria junto.
    """
    await session.execute(select(func.pg_advisory_xact_lock(_BUDGET_LOCK_KEY)))
    try:
        await _check_budget(session, budget_for(call.purpose), call.cost_usd or Decimal(0))
    except LLMBudgetExceededError:
        # Commit, não rollback: só houve leituras, e o rollback expiraria os objetos da sessão.
        await session.commit()
        raise
    session.add(call)
    await session.commit()
