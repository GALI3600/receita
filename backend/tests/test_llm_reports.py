"""Relatórios sobre `llm_calls`: gasto por versão do prompt e simulação do TTL do cache."""

import contextlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.models import LLMCall, LLMPurpose
from app.models.llm_call import LLM_CALL_IN_PROGRESS, LLM_CALL_TIMEOUT
from app.services import llm_reports, quotas
from app.services.llm_reports import simulate_hits
from tests.factories import make_video

NOW = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
T0 = datetime(2026, 5, 10, 9, 0, tzinfo=UTC)
OPUS = "claude-opus-5-5"


def _min(*minutes: float) -> list[datetime]:
    return [T0 + timedelta(minutes=m) for m in minutes]


@pytest.mark.parametrize(
    ("starts", "hits_5m", "hits_1h"),
    [
        (_min(0, 4, 8), [False, True, True], [False, True, True]),
        (_min(0, 30), [False, False], [False, True]),
        # Cada leitura renova o TTL: a cadeia a cada 4 min mantém o cache de 5 min vivo.
        (_min(0, 4, 8, 12, 16, 20), [False] + [True] * 5, [False] + [True] * 5),
        # A escrita só fica legível depois de começar a resposta: a 2ª chamada também escreve.
        (_min(0, 1 / 60, 11 / 60), [False, False, True], [False, False, True]),
        # A escrita de 5 min expirou e a nova vale a partir dela; a de 1 h foi renovada até 67.
        (_min(0, 6, 7, 70), [False, False, True, False], [False, True, True, False]),
        ([], [], []),
    ],
    ids=["4-min", "30-min", "cadeia", "simultaneas", "reescrita", "vazio"],
)
def test_simulate_hits(starts: list[datetime], hits_5m: list[bool], hits_1h: list[bool]) -> None:
    assert simulate_hits(starts, 300, 5) == hits_5m
    assert simulate_hits(starts, 3600, 5) == hits_1h


def _usage(
    *, input_tokens: int = 1000, output: int = 2000, read: int = 0, write: int = 0, **extra: Any
) -> dict[str, Any]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
        "cache_creation": {"ephemeral_5m_input_tokens": write, "ephemeral_1h_input_tokens": 0},
        **extra,
    }


async def _add_calls(session: AsyncSession, *calls: dict[str, Any]) -> None:
    video = await make_video(session)
    for fields in calls:
        defaults: dict[str, Any] = {
            "model": OPUS,
            "prompt_version": "v1",
            "purpose": LLMPurpose.IMPORT,
            "effort": "medium",
            "usage": {},
            "started_at": T0,
        }
        session.add(LLMCall(video_id=video.id, **(defaults | fields)))
    await session.commit()


async def test_cache_sim_costs(session: AsyncSession) -> None:
    prefix = 6000
    await _add_calls(
        session,
        {"started_at": T0, "usage": _usage(write=prefix)},
        {"started_at": T0 + timedelta(minutes=4), "usage": _usage(read=prefix)},
        {"started_at": T0 + timedelta(minutes=30), "usage": _usage(write=prefix)},
        # Em andamento: entra na linha do tempo (acerta nas duas políticas), não no custo.
        {"started_at": T0 + timedelta(minutes=31), "error_code": LLM_CALL_IN_PROGRESS},
        # O eval fica de fora; outra versão do prompt é outro prefixo.
        {"started_at": T0 + timedelta(minutes=5), "purpose": LLMPurpose.EVAL, "usage": _usage()},
        {"started_at": T0 + timedelta(minutes=6), "prompt_version": "v2", "usage": _usage()},
    )

    v1, v2 = await llm_reports.cache_sim(session, days=1, now=NOW)

    assert (v1.prompt_version, v1.calls, v1.priced, v1.real_hits) == ("v1", 4, 3, 1)
    assert (v1.hits_5m, v1.hits_1h) == (2, 3)
    # Opus 5.5 (US$/MTok): entrada 4, saída 20, leitura 0,20, escrita 5 (5 min) ou 8 (1 h).
    # Cada linha paga 1000 de entrada e 2000 de saída (0,044) mais o prefixo de 6000.
    base, read = Decimal("0.044"), Decimal("0.0012")
    write_5m, write_1h = Decimal("0.03"), Decimal("0.048")
    assert v1.cost_none_usd == 3 * (base + Decimal("0.024"))
    assert v1.cost_5m_usd == (base + write_5m) + (base + read) + (base + write_5m)
    assert v1.cost_1h_usd == (base + write_1h) + (base + read) + (base + read)
    assert v1.cost_real_usd == v1.cost_5m_usd
    # Sem cache gravado no usage (sem marcador): o prefixo vem do maior do grupo, então nada
    # muda no v2, que só tem essa linha.
    assert (v2.prompt_version, v2.calls, v2.priced) == ("v2", 1, 1)
    assert v2.cost_none_usd == v2.cost_5m_usd == v2.cost_1h_usd == v2.cost_real_usd == base


async def test_cache_sim_prices_rows_without_marker_with_the_group_prefix(
    session: AsyncSession,
) -> None:
    await _add_calls(
        session,
        {"started_at": T0, "usage": _usage(write=6000)},
        # Sem marcador: os 6000 do prefixo estão na entrada.
        {"started_at": T0 + timedelta(minutes=2), "usage": _usage(input_tokens=7000)},
    )

    [group] = await llm_reports.cache_sim(session, days=1, now=NOW)

    second_none = Decimal("0.044") + Decimal("0.024")
    assert group.cost_none_usd == 2 * second_none
    assert group.cost_5m_usd == (Decimal("0.044") + Decimal("0.03")) + (
        Decimal("0.044") + Decimal("0.0012")
    )
    assert group.cost_real_usd == Decimal("0.044") + Decimal("0.03") + second_none


async def test_cache_sim_keeps_batch_and_geo_multipliers(session: AsyncSession) -> None:
    await _add_calls(session, {"usage": _usage(write=6000, service_tier="batch")})

    [group] = await llm_reports.cache_sim(session, days=1, now=NOW)

    assert group.cost_5m_usd == (Decimal("0.044") + Decimal("0.03")) / 2
    assert group.cost_none_usd == (Decimal("0.044") + Decimal("0.024")) / 2


async def test_spend_by_version(session: AsyncSession) -> None:
    ok_usage = _usage(read=6000, output_tokens_details={"thinking_tokens": 500})
    old_usage = _usage(output=1000)
    await _add_calls(
        session,
        {"usage": ok_usage, "cost_usd": Decimal("0.05"), "max_tokens": 20000},
        {
            "started_at": T0 + timedelta(minutes=1),
            "usage": _usage(output=3000),
            "cost_usd": Decimal("0.07"),
            "max_tokens": 20000,
        },
        {
            "started_at": T0 + timedelta(minutes=2),
            "usage": _usage(output=20000),
            "error_code": "llm_output_too_long",
            "stop_reason": "max_tokens",
            "cost_usd": Decimal("0.4"),
            "max_tokens": 20000,
        },
        {
            "started_at": T0 + timedelta(minutes=3),
            "error_code": LLM_CALL_TIMEOUT,
            "cost_usd": Decimal("0.3"),
        },
        {
            "started_at": T0 + timedelta(minutes=4),
            "error_code": LLM_CALL_IN_PROGRESS,
            "cost_usd": Decimal("0.3"),
        },
        # Linha anterior à coluna cost_usd: custo calculado do usage.
        {"started_at": T0 - timedelta(hours=1), "prompt_version": "v0", "usage": old_usage},
        {"started_at": T0 + timedelta(minutes=5), "purpose": LLMPurpose.EVAL, "usage": _usage()},
        # Fora da janela.
        {"started_at": T0 - timedelta(days=3), "prompt_version": "v-1", "usage": _usage()},
    )

    report = await llm_reports.spend_by_version(session, days=2, now=NOW)

    assert [(r.prompt_version, r.purpose) for r in report] == [
        ("v0", "import"),
        ("v1", "import"),
        ("v1", "eval"),
    ]
    old, v1, _ = report
    assert old.cost_usd == quotas.llm_cost_usd(OPUS, old_usage)
    assert (old.ok, old.max_tokens, old.cut) == (1, None, 0)
    assert (v1.calls, v1.ok, v1.unanswered, v1.cut) == (5, 2, 2, 1)
    assert v1.cost_usd == Decimal("1.12")
    assert v1.cost_per_ok_usd == Decimal("0.56")
    assert (v1.output_tokens, v1.thinking_tokens) == (25000, 500)
    assert v1.thinking_share == pytest.approx(0.02)
    assert (v1.cache_hits, v1.with_usage, v1.hit_rate) == (1, 3, pytest.approx(1 / 3))
    assert (v1.p95_output, v1.max_tokens, v1.p95_share) == (20000, 20000, 1.0)


async def test_lost_calls(session: AsyncSession) -> None:
    await _add_calls(
        session,
        {"started_at": NOW - timedelta(hours=2), "error_code": LLM_CALL_IN_PROGRESS},
        {"started_at": NOW - timedelta(minutes=10), "error_code": LLM_CALL_IN_PROGRESS},
        {"started_at": NOW - timedelta(hours=3), "error_code": LLM_CALL_TIMEOUT},
    )

    assert await llm_reports.lost_calls(session, days=1, now=NOW) == 1


def test_nearest_rank() -> None:
    assert llm_reports.nearest_rank([], 0.95) is None
    assert llm_reports.nearest_rank([5], 0.95) == 5
    assert llm_reports.nearest_rank(list(range(1, 21)), 0.95) == 19
    assert llm_reports.nearest_rank(list(range(1, 101)), 0.95) == 95


class _Engine:
    async def dispose(self) -> None:
        pass


def test_cli_llm_spend_by_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    row = llm_reports.VersionSpend(
        prompt_version="2026-10-14.2",
        model=OPUS,
        purpose="import",
        calls=4,
        ok=2,
        unanswered=1,
        cut=1,
        cost_usd=Decimal("0.5"),
        output_tokens=10000,
        thinking_tokens=2500,
        cache_hits=1,
        with_usage=2,
        p95_output=8000,
        max_tokens=20000,
        first_started_at=T0,
    )

    async def spend_by_version(session: Any, days: int) -> list[llm_reports.VersionSpend]:
        return [row]

    async def lost_calls(session: Any, days: int) -> int:
        return 3

    monkeypatch.setattr(llm_reports, "spend_by_version", spend_by_version)
    monkeypatch.setattr(llm_reports, "lost_calls", lost_calls)
    monkeypatch.setattr(cli, "SessionLocal", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(cli, "engine", _Engine())

    assert cli.main(["llm-spend", "--by", "version", "--days", "3"]) == 0

    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if line.startswith("2026-10-14.2"))
    assert line.split() == [
        "2026-10-14.2", OPUS, "import", "4", "2", "1", "0.5000", "0.2500", "10000", "25%",
        "50%", "8000", "40%", "1",
    ]  # fmt: skip
    assert "perdidas (llm_in_progress há mais de 1 h, contam a estimativa): 3" in out


def test_cli_llm_cache_sim(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    group = llm_reports.CacheSimGroup(
        model=OPUS,
        prompt_version="v1",
        effort="medium",
        calls=4,
        priced=4,
        real_hits=1,
        hits_5m=2,
        hits_1h=3,
        cost_real_usd=Decimal("0.4"),
        cost_none_usd=Decimal("0.5"),
        cost_5m_usd=Decimal("0.4"),
        cost_1h_usd=Decimal("0.3"),
    )
    seen: list[tuple[int, float]] = []

    async def cache_sim(
        session: Any, days: int, readable_after_s: float
    ) -> list[llm_reports.CacheSimGroup]:
        seen.append((days, readable_after_s))
        return [group, group]

    monkeypatch.setattr(llm_reports, "cache_sim", cache_sim)
    monkeypatch.setattr(cli, "SessionLocal", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(cli, "engine", _Engine())

    assert cli.main(["llm-cache-sim"]) == 0

    assert seen == [(14, 5.0)]
    lines = capsys.readouterr().out.splitlines()
    row = next(line for line in lines if line.startswith(OPUS))
    assert row.split() == [OPUS, "v1", "medium", "4", "25%", "50%", "75%", "0.4000", "0.5000",
                           "0.4000", "0.3000"]  # fmt: skip
    total = next(line for line in lines if line.startswith("total"))
    assert total.split()[1:] == ["8", "25%", "50%", "75%", "0.8000", "1.0000", "0.8000", "0.6000"]
    assert any("51%" in line for line in lines)
