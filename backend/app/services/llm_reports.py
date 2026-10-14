"""Relatórios sobre `llm_calls` para o CLI: gasto por versão do prompt e simulação do TTL do cache.

Só leitura. As janelas contam dias UTC pelo `started_at` (início da chamada; nas linhas
anteriores à coluna, o `created_at`).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LLMCall, LLMPurpose
from app.models.llm_call import LLM_CALL_IN_PROGRESS, LLM_CALL_TIMEOUT
from app.services.quotas import day_start, llm_cost_usd, row_cost

# Uma reserva `llm_in_progress` mais velha que isso é dada como perdida (o processo morreu). Não
# é o prazo do job: CLI e eval não têm um, e com os retries de timeout do SDK uma chamada
# legítima pode levar 600 s × (1 + MAX_RETRIES), uns 40 min.
LOST_CALL_AFTER = timedelta(hours=1)


def _since(days: int, now: datetime | None) -> datetime:
    return day_start(now) - timedelta(days=days - 1)


def _tokens(usage: dict[str, Any], name: str) -> int:
    value = usage.get(name)
    return value if isinstance(value, int) and value > 0 else 0


def thinking_tokens(usage: dict[str, Any]) -> int:
    details = usage.get("output_tokens_details")
    return _tokens(details, "thinking_tokens") if isinstance(details, dict) else 0


def nearest_rank(values: Sequence[int], q: float) -> int | None:
    """Percentil `q` (0–1) pelo método nearest-rank; `None` sem valores."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(q * len(ordered))) - 1]


# --- Gasto por versão do prompt ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VersionSpend:
    prompt_version: str
    model: str
    purpose: str
    calls: int
    ok: int
    # Em andamento ou interrompidas: contam com o custo estimado.
    unanswered: int
    # stop_reason "max_tokens". As linhas anteriores à coluna não têm stop_reason: os cortes
    # delas foram gravados como llm_invalid_output.
    cut: int
    # Soma de todas as linhas, inclusive falhas pagas e estimativas.
    cost_usd: Decimal
    output_tokens: int
    thinking_tokens: int
    cache_hits: int
    # Linhas com usage (o denominador do acerto do cache).
    with_usage: int
    p95_output: int | None
    max_tokens: int | None
    first_started_at: datetime

    @property
    def cost_per_ok_usd(self) -> Decimal | None:
        return self.cost_usd / self.ok if self.ok else None

    @property
    def thinking_share(self) -> float | None:
        return self.thinking_tokens / self.output_tokens if self.output_tokens else None

    @property
    def hit_rate(self) -> float | None:
        return self.cache_hits / self.with_usage if self.with_usage else None

    @property
    def p95_share(self) -> float | None:
        if self.p95_output is None or not self.max_tokens:
            return None
        return self.p95_output / self.max_tokens


async def spend_by_version(
    session: AsyncSession, days: int, now: datetime | None = None
) -> list[VersionSpend]:
    """Gasto dos últimos `days` dias UTC por `prompt_version` × modelo × `purpose`, na ordem em
    que cada grupo apareceu. O modelo é o que respondeu (com fallback, o do fallback)."""
    rows = await session.execute(
        select(
            LLMCall.prompt_version,
            LLMCall.model,
            LLMCall.purpose,
            LLMCall.error_code,
            LLMCall.stop_reason,
            LLMCall.usage,
            LLMCall.cost_usd,
            LLMCall.max_tokens,
            LLMCall.started_at,
        ).where(LLMCall.started_at >= _since(days, now))
    )
    groups: dict[tuple[str, str, str], list[Any]] = {}
    for row in rows:
        groups.setdefault((row.prompt_version, row.model, str(row.purpose)), []).append(row)

    report = []
    for (prompt_version, model, purpose), members in groups.items():
        priced = [row.usage for row in members if row.usage]
        outputs = [_tokens(usage, "output_tokens") for usage in priced]
        ceilings = [row.max_tokens for row in members if row.max_tokens is not None]
        report.append(
            VersionSpend(
                prompt_version=prompt_version,
                model=model,
                purpose=purpose,
                calls=len(members),
                ok=sum(row.error_code is None for row in members),
                unanswered=sum(
                    row.error_code in (LLM_CALL_IN_PROGRESS, LLM_CALL_TIMEOUT) for row in members
                ),
                cut=sum(row.stop_reason == "max_tokens" for row in members),
                cost_usd=sum(
                    (row_cost(row.model, row.usage, row.cost_usd) for row in members), Decimal(0)
                ),
                output_tokens=sum(outputs),
                thinking_tokens=sum(thinking_tokens(usage) for usage in priced),
                cache_hits=sum(_tokens(usage, "cache_read_input_tokens") > 0 for usage in priced),
                with_usage=len(priced),
                p95_output=nearest_rank(outputs, 0.95),
                max_tokens=max(ceilings, default=None),
                first_started_at=min(row.started_at for row in members),
            )
        )
    return sorted(report, key=lambda spend: spend.first_started_at)


async def lost_calls(session: AsyncSession, days: int, now: datetime | None = None) -> int:
    """Reservas `llm_in_progress` da janela começadas há mais de `LOST_CALL_AFTER`."""
    now = now or datetime.now(UTC)
    count = await session.scalar(
        select(func.count()).where(
            LLMCall.error_code == LLM_CALL_IN_PROGRESS,
            LLMCall.started_at >= _since(days, now),
            LLMCall.started_at < now - LOST_CALL_AFTER,
        )
    )
    return count or 0


# --- Simulação do TTL do cache ----------------------------------------------------------------

# Tráfego de produção e do CLI; o eval roda em rajadas sequenciais e distorceria o acerto.
CACHE_SIM_PURPOSES = (LLMPurpose.IMPORT, LLMPurpose.DEFERRED, LLMPurpose.CLI)
TTL_5M_S = 300.0
TTL_1H_S = 3600.0


def simulate_hits(starts: list[datetime], ttl_s: float, readable_after_s: float) -> list[bool]:
    """Acerto de cache de cada chamada, em ordem de início, com um único prefixo.

    O TTL conta do início da chamada e renova a cada leitura [PC]; uma escrita só fica legível
    depois que a resposta começa, então chamadas iniciadas a menos de `readable_after_s` da
    escrita também escrevem.
    """
    ttl = timedelta(seconds=ttl_s)
    readable_after = timedelta(seconds=readable_after_s)
    expires: datetime | None = None
    readable_from: datetime | None = None
    hits = []
    for t in starts:
        if expires is not None and readable_from is not None and readable_from <= t < expires:
            hits.append(True)
            expires = max(expires, t + ttl)
            continue
        hits.append(False)
        if expires is None or t >= expires:
            readable_from = t + readable_after
        expires = max(expires or t, t + ttl)
    return hits


@dataclass(frozen=True, slots=True)
class CacheSimGroup:
    model: str
    prompt_version: str
    effort: str | None
    # Todas as linhas do grupo: as sem usage (em andamento, interrompidas) entram na linha do
    # tempo, mas não no custo.
    calls: int
    priced: int
    real_hits: int
    hits_5m: int
    hits_1h: int
    # Custo do usage do topo, como gravado. Com fallback, só a última tentativa entra (aqui e
    # nas políticas), para a comparação ser justa.
    cost_real_usd: Decimal
    # Sem marcador: o prefixo pago como entrada.
    cost_none_usd: Decimal
    cost_5m_usd: Decimal
    cost_1h_usd: Decimal


def _prefix(usage: dict[str, Any]) -> int:
    return _tokens(usage, "cache_read_input_tokens") + _tokens(usage, "cache_creation_input_tokens")


def _top(usage: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in usage.items() if key != "iterations"}


def _with_cache(
    usage: dict[str, Any], *, input_tokens: int, read: int, write: int, write_1h: int
) -> dict[str, Any]:
    return _top(usage) | {
        "input_tokens": input_tokens,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
        "cache_creation": {
            "ephemeral_5m_input_tokens": write - write_1h,
            "ephemeral_1h_input_tokens": write_1h,
        },
    }


def _policy_costs(
    model: str, usage: dict[str, Any], prefix: int, *, hit_5m: bool, hit_1h: bool
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """(real, sem marcador, 5m, 1h) de uma linha com usage."""
    message = _tokens(usage, "input_tokens")
    if not _prefix(usage):
        # Gravada sem marcador: o prefixo já está na entrada.
        message = max(0, message - prefix)

    def cost(*, read: int = 0, write: int = 0, write_1h: int = 0, extra: int = 0) -> Decimal:
        fields = _with_cache(
            usage, input_tokens=message + extra, read=read, write=write, write_1h=write_1h
        )
        return llm_cost_usd(model, fields)

    hit = cost(read=prefix)
    return (
        llm_cost_usd(model, _top(usage)),
        cost(extra=prefix),
        hit if hit_5m else cost(write=prefix),
        hit if hit_1h else cost(write=prefix, write_1h=prefix),
    )


async def cache_sim(
    session: AsyncSession,
    days: int,
    readable_after_s: float = 5.0,
    now: datetime | None = None,
) -> list[CacheSimGroup]:
    """Acerto e custo do cache com TTL de 5 min e de 1 h sobre as chamadas reais da janela, por
    modelo × `prompt_version` × effort (cada um com seu prefixo)."""
    rows = await session.execute(
        select(
            LLMCall.model,
            LLMCall.prompt_version,
            LLMCall.effort,
            LLMCall.started_at,
            LLMCall.usage,
        )
        .where(
            LLMCall.purpose.in_(list(CACHE_SIM_PURPOSES)),
            LLMCall.started_at >= _since(days, now),
        )
        .order_by(LLMCall.started_at)
    )
    groups: dict[tuple[str, str, str | None], list[Any]] = {}
    for row in rows:
        groups.setdefault((row.model, row.prompt_version, row.effort), []).append(row)

    report = []
    for (model, prompt_version, effort), members in groups.items():
        starts = [row.started_at for row in members]
        hits_5m = simulate_hits(starts, TTL_5M_S, readable_after_s)
        hits_1h = simulate_hits(starts, TTL_1H_S, readable_after_s)
        largest_prefix = max((_prefix(row.usage) for row in members), default=0)
        costs = [
            _policy_costs(
                model,
                row.usage,
                _prefix(row.usage) or largest_prefix,
                hit_5m=hit_5m,
                hit_1h=hit_1h,
            )
            for row, hit_5m, hit_1h in zip(members, hits_5m, hits_1h, strict=True)
            if row.usage
        ]

        def total(index: int, costs: list[tuple[Decimal, ...]] = costs) -> Decimal:
            return sum((row[index] for row in costs), Decimal(0))

        report.append(
            CacheSimGroup(
                model=model,
                prompt_version=prompt_version,
                effort=effort,
                calls=len(members),
                priced=len(costs),
                real_hits=sum(_tokens(row.usage, "cache_read_input_tokens") > 0 for row in members),
                hits_5m=sum(hits_5m),
                hits_1h=sum(hits_1h),
                cost_real_usd=total(0),
                cost_none_usd=total(1),
                cost_5m_usd=total(2),
                cost_1h_usd=total(3),
            )
        )
    return report
