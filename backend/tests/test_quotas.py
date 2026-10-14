"""Cota diária de receitas novas por usuário e custo/orçamento do Claude."""

import asyncio
import contextlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from arq.connections import ArqRedis
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import cli, queue
from app.config import Settings
from app.errors import LLMBudgetExceededError
from app.models import Import, ImportStatus, LLMCall, LLMPurpose, User, Video
from app.models.llm_call import LLM_CALL_IN_PROGRESS, LLM_CALL_TIMEOUT
from app.services import quotas
from tests.factories import headers, make_user, make_video, youtube_id


def _url(n: int) -> str:
    return f"https://youtu.be/{youtube_id(n)}"


async def _add_import(
    session: AsyncSession,
    user: User,
    n: int,
    status: ImportStatus,
    charged_at: datetime | None = None,
) -> Import:
    imp = Import(
        user_id=user.id,
        url=_url(n),
        youtube_id=youtube_id(n),
        status=status,
        charged_at=charged_at,
    )
    session.add(imp)
    await session.commit()
    return imp


async def _quota(client: AsyncClient, user: User) -> dict[str, Any]:
    response = await client.get("/auth/me", headers=headers(user))
    return response.json()["quota"]


# --- Cota por usuário -------------------------------------------------------------------------


async def test_quota_counts_new_recipes_of_today_and_unfinished_imports(
    client: AsyncClient, session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "daily_import_limit", 5)
    user, other = await make_user(session), await make_user(session, "Bia")
    now = datetime.now(UTC)
    await _add_import(session, user, 1, ImportStatus.DONE, charged_at=now)
    await _add_import(session, user, 2, ImportStatus.DONE, charged_at=now - timedelta(days=1))
    await _add_import(session, user, 3, ImportStatus.DONE)  # cópia
    await _add_import(session, user, 4, ImportStatus.FAILED)
    await _add_import(session, user, 5, ImportStatus.TRANSCRIBING)
    await _add_import(session, user, 6, ImportStatus.DEFERRED)
    await _add_import(session, other, 7, ImportStatus.DONE, charged_at=now)

    quota = await _quota(client, user)

    assert (quota["used"], quota["limit"], quota["remaining"]) == (3, 5, 2)


async def test_import_over_quota_is_rejected(
    client: AsyncClient,
    session: AsyncSession,
    redis: ArqRedis,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "daily_import_limit", 2)
    user = await make_user(session)
    await _add_import(session, user, 1, ImportStatus.DONE, charged_at=datetime.now(UTC))
    await _add_import(session, user, 2, ImportStatus.PENDING)

    response = await client.post("/imports", headers=headers(user), json={"url": _url(3)})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "quota_exceeded"
    retry_after = int(response.headers["Retry-After"])
    assert 0 < retry_after <= 86400
    assert retry_after == pytest.approx(quotas.seconds_until_tomorrow(), abs=5)
    assert await session.scalar(select(func.count()).select_from(Import)) == 2
    assert await redis.queued_jobs() == []


async def test_copies_do_not_need_nor_use_quota(
    client: AsyncClient, session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "daily_import_limit", 1)
    user = await make_user(session)
    await _add_import(session, user, 1, ImportStatus.DONE, charged_at=datetime.now(UTC))
    await make_video(session, youtube_id(2))

    response = await client.post("/imports", headers=headers(user), json={"url": _url(2)})

    assert response.status_code == 200
    assert response.json()["status"] == "done"
    imp = await session.get(Import, uuid.UUID(response.json()["id"]))
    assert imp is not None and imp.charged_at is None
    assert (await _quota(client, user))["used"] == 1


async def test_failures_do_not_use_quota(
    client: AsyncClient,
    session: AsyncSession,
    redis: ArqRedis,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "daily_import_limit", 1)
    user = await make_user(session)
    for n in range(3):
        await _add_import(session, user, n, ImportStatus.FAILED)

    response = await client.post("/imports", headers=headers(user), json={"url": _url(9)})

    assert response.status_code == 202


async def test_same_video_in_progress_does_not_need_more_quota(
    client: AsyncClient, session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "daily_import_limit", 1)
    user = await make_user(session)
    deferred = await _add_import(session, user, 1, ImportStatus.DEFERRED)

    response = await client.post("/imports", headers=headers(user), json={"url": _url(1)})

    assert response.status_code == 200
    assert response.json()["id"] == str(deferred.id)
    assert response.json()["status"] == "deferred"


async def test_simultaneous_imports_do_not_exceed_quota(
    client: AsyncClient,
    session: AsyncSession,
    redis: ArqRedis,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "daily_import_limit", 2)
    user = await make_user(session)

    responses = await asyncio.gather(
        *(client.post("/imports", headers=headers(user), json={"url": _url(n)}) for n in range(6))
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [202, 202, 429, 429, 429, 429]
    assert await session.scalar(select(func.count()).select_from(Import)) == 2
    assert len(await redis.queued_jobs(queue_name=queue.DEFAULT_QUEUE)) == 2


async def test_zero_limit_blocks_new_recipes(
    client: AsyncClient, session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "daily_import_limit", 0)
    user = await make_user(session)

    response = await client.post("/imports", headers=headers(user), json={"url": _url(1)})

    assert response.status_code == 429


def test_day_boundaries_are_utc() -> None:
    late_in_brazil = datetime(2026, 10, 13, 23, 30, tzinfo=UTC) - timedelta(hours=3)
    assert quotas.day_start(late_in_brazil) == datetime(2026, 10, 13, tzinfo=UTC)
    assert quotas.next_day_start(late_in_brazil) == datetime(2026, 10, 14, tzinfo=UTC)
    assert quotas.seconds_until_tomorrow(datetime(2026, 10, 13, 23, 59, tzinfo=UTC)) == 60


# --- Custo e orçamento do Claude --------------------------------------------------------------


def test_cost_of_plain_usage() -> None:
    usage = {"input_tokens": 5000, "output_tokens": 2500}

    # 5000 × US$ 4/MTok + 2500 × US$ 20/MTok
    assert quotas.llm_cost_usd("claude-opus-5-5", usage) == Decimal("0.07")


def test_cost_with_cache() -> None:
    usage = {
        "input_tokens": 1000,
        "output_tokens": 1000,
        "cache_read_input_tokens": 100_000,
        "cache_creation_input_tokens": 3000,
        "cache_creation": {"ephemeral_5m_input_tokens": 2000, "ephemeral_1h_input_tokens": 1000},
        "service_tier": "standard",
    }

    expected = (
        Decimal(1000 * 4 + 1000 * 20) + Decimal("0.20") * 100_000 + 2000 * 5 + 1000 * 8
    ) / 1_000_000
    assert quotas.llm_cost_usd("claude-opus-5-5", usage) == expected


def test_cache_write_without_breakdown_counts_as_5_minutes() -> None:
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 1_000_000}

    assert quotas.llm_cost_usd("claude-opus-5-5", usage) == Decimal(5)


def test_cost_with_server_side_fallback_sums_every_attempt() -> None:
    usage = {
        "input_tokens": 1000,
        "output_tokens": 500,
        "iterations": [
            {
                "type": "message",
                "model": "claude-opus-5-5",
                "input_tokens": 1000,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            {
                "type": "fallback_message",
                "model": "claude-opus-5",
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        ],
    }

    expected = (Decimal(1000 * 4) + Decimal(1000 * 5 + 500 * 25)) / 1_000_000
    assert quotas.llm_cost_usd("claude-opus-5", usage) == expected


def test_unknown_model_is_priced_conservatively() -> None:
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}

    assert quotas.llm_cost_usd("modelo-novo", usage) == Decimal(60)


def test_unknown_model_uses_highest_published_price_per_category(
    caplog: pytest.LogCaptureFixture,
) -> None:
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 1_000_000}

    # Leitura do cache mais cara é a do Opus 5/4.8, não a do Fable 5.1 (o de entrada mais cara).
    assert quotas.llm_cost_usd("modelo-novo", usage) == Decimal("0.50")
    assert "modelo-novo sem preço cadastrado" in caplog.text


MTOK_EACH = {
    "input_tokens": 1_000_000,
    "output_tokens": 1_000_000,
    "cache_read_input_tokens": 1_000_000,
}


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("claude-sonnet-5-5", "12.10"),
        ("claude-sonnet-5", "12.20"),
        ("claude-haiku-4-5", "6.10"),
        ("claude-fable-5-1", "60.25"),
        ("claude-opus-4-8", "30.50"),
    ],
)
def test_prices_per_model(model: str, expected: str) -> None:
    assert quotas.llm_cost_usd(model, MTOK_EACH) == Decimal(expected)


def test_haiku_5_5_long_prompt_tier_applies_to_whole_request() -> None:
    short = {"input_tokens": 50_000, "cache_read_input_tokens": 40_000, "output_tokens": 1000}
    long = {"input_tokens": 60_000, "cache_read_input_tokens": 41_000, "output_tokens": 1000}

    assert quotas.llm_cost_usd("claude-haiku-5-5", short) == Decimal("0.0059")
    # 101k de prompt: entrada, leitura e saída, todas no preço de prompt longo.
    assert quotas.llm_cost_usd("claude-haiku-5-5", long) == Decimal("0.03455")


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, "24"),
        ({"service_tier": "standard", "inference_geo": "global"}, "24"),
        ({"service_tier": "batch"}, "12"),
        ({"inference_geo": "us"}, "26.4"),
        ({"service_tier": "batch", "inference_geo": "us"}, "13.2"),
    ],
)
def test_batch_and_us_geo_multipliers_stack(fields: dict[str, str], expected: str) -> None:
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, **fields}
    with_writes = {
        **usage,
        "cache_creation_input_tokens": 2_000_000,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 1_000_000,
            "ephemeral_1h_input_tokens": 1_000_000,
        },
    }

    assert quotas.llm_cost_usd("claude-opus-5-5", usage) == Decimal(expected)
    # Escrita de 5 min (US$ 5) e de 1 h (US$ 8) recebem os mesmos multiplicadores.
    factor = Decimal(expected) / 24
    assert quotas.llm_cost_usd("claude-opus-5-5", with_writes) == 37 * factor


def test_iteration_fields_override_top_level() -> None:
    usage = {
        "service_tier": "standard",
        "inference_geo": "us",
        "iterations": [
            {"model": "claude-opus-5-5", "input_tokens": 1_000_000, "service_tier": "batch"},
            {"model": "claude-opus-5-5", "input_tokens": 1_000_000, "inference_geo": "global"},
        ],
    }

    # Batch herda o geo "us" do topo (4 × 0,5 × 1,1); a outra fica standard e global.
    assert quotas.llm_cost_usd("claude-opus-5-5", usage) == Decimal("2.2") + 4


def test_fallback_iterations_inherit_1h_cache_write() -> None:
    def usage(top_1h: int) -> dict[str, Any]:
        return {
            "cache_creation_input_tokens": 1000,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 1000 - top_1h,
                "ephemeral_1h_input_tokens": top_1h,
            },
            "iterations": [
                {"model": "claude-opus-5-5", "cache_creation_input_tokens": 1_000_000},
                {"model": "claude-opus-5", "input_tokens": 1_000_000},
            ],
        }

    # As iterations só trazem o total da escrita: com marcador de 1 h, ela custa 2× a entrada.
    assert quotas.llm_cost_usd("claude-opus-5", usage(1000)) == Decimal(8 + 5)
    assert quotas.llm_cost_usd("claude-opus-5", usage(0)) == Decimal(5 + 5)


def test_request_cache_marker_prices_writes_of_refused_attempt() -> None:
    # O modelo do fallback leu o próprio cache: o topo não escreveu nada, mas a tentativa
    # recusada escreveu o prefixo com o marcador de 1 h.
    usage = {
        "cache_creation_input_tokens": 0,
        "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0},
        "iterations": [
            {"model": "claude-opus-5-5", "cache_creation_input_tokens": 1_000_000},
            {"model": "claude-opus-5", "cache_read_input_tokens": 1_000_000},
        ],
    }

    assert quotas.llm_cost_usd("claude-opus-5", usage, cache_ttl="1h") == Decimal("8.5")
    assert quotas.llm_cost_usd("claude-opus-5", usage, cache_ttl="5m") == Decimal("5.5")
    # Sem o marcador (linhas antigas), fica o TTL do topo.
    assert quotas.llm_cost_usd("claude-opus-5", usage) == Decimal("5.5")


def test_estimate_cost_prices_prefix_as_cache_write() -> None:
    def estimate(cache_ttl: str | None, cache_hit: bool = False) -> Decimal:
        return quotas.estimate_cost_usd(
            "claude-opus-5-5",
            prefix_tokens=1_000_000,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_ttl=cache_ttl,
            cache_hit=cache_hit,
        )

    assert estimate(None) == Decimal(8 + 20)
    assert estimate("5m") == Decimal(4 + 5 + 20)
    assert estimate("1h") == Decimal(4 + 8 + 20)
    assert estimate("5m", cache_hit=True) == Decimal("24.2")
    assert estimate("1h", cache_hit=True) == Decimal("24.2")


def test_estimate_cost_uses_long_prompt_tier_for_haiku() -> None:
    cost = quotas.estimate_cost_usd(
        "claude-haiku-5-5",
        prefix_tokens=60_000,
        input_tokens=50_000,
        output_tokens=1000,
        cache_ttl="5m",
    )

    # 110k de prompt: 50k × 0,50 + 60k × 0,625 (escrita de 5 min) + 1k × 2,50
    assert cost == Decimal("0.065")


def _call(
    video: Video,
    usage: dict[str, Any] | None = None,
    purpose: LLMPurpose = LLMPurpose.IMPORT,
    **fields: Any,
) -> LLMCall:
    return LLMCall(
        video_id=video.id,
        model="claude-opus-5-5",
        prompt_version="v",
        usage=usage if usage is not None else {},
        purpose=purpose,
        **fields,
    )


async def test_spend_today_ignores_previous_days(session: AsyncSession) -> None:
    video = await make_video(session)
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    session.add_all(
        [
            _call(video, usage),
            _call(video, usage, error_code="llm_refused"),
            _call(video, usage, created_at=datetime.now(UTC) - timedelta(days=1)),
        ]
    )
    await session.commit()

    assert await quotas.llm_spend_today(session) == Decimal(8)


async def test_budget_check(
    session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = await make_video(session)
    session.add(_call(video, {"input_tokens": 0, "output_tokens": 100_000}))  # US$ 2
    await session.commit()

    monkeypatch.setattr(settings, "daily_llm_budget_usd", 2.5)
    assert await quotas.llm_budget_available(session)
    assert await quotas.llm_budget_available(session, Decimal("0.5"))
    assert not await quotas.llm_budget_available(session, Decimal("0.6"))
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 2.0)
    assert not await quotas.llm_budget_available(session)


async def test_copies_keep_working_without_budget(
    client: AsyncClient, session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 0)
    user = await make_user(session)
    await make_video(session, youtube_id(1))

    response = await client.post("/imports", headers=headers(user), json={"url": _url(1)})

    assert response.status_code == 200
    assert response.json()["status"] == "done"


async def test_spend_by_day(session: AsyncSession) -> None:
    video = await make_video(session)
    now = datetime(2026, 5, 10, 15, tzinfo=UTC)
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}

    def call(created_at: datetime, error_code: str | None = None) -> LLMCall:
        return _call(video, usage, error_code=error_code, created_at=created_at)

    session.add_all(
        [
            call(now - timedelta(hours=1)),
            call(now - timedelta(hours=2), "llm_refused"),
            call(now - timedelta(days=2)),
            call(now - timedelta(days=5)),  # fora da janela de 3 dias
        ]
    )
    await session.commit()

    report = await quotas.llm_spend_by_day(session, 3, now=now)

    assert [
        (
            s.day.isoformat(),
            s.calls,
            s.failed_calls,
            s.unfinished_calls,
            s.cost_usd,
            s.eval_cost_usd,
        )
        for s in report
    ] == [
        ("2026-05-10", 2, 1, 0, Decimal(8), Decimal(0)),
        ("2026-05-09", 0, 0, 0, Decimal(0), Decimal(0)),
        ("2026-05-08", 1, 0, 0, Decimal(4), Decimal(0)),
    ]


async def test_spend_by_day_separates_eval_and_unfinished_calls(session: AsyncSession) -> None:
    video = await make_video(session)
    now = datetime(2026, 5, 10, 15, tzinfo=UTC)
    created_at = now - timedelta(hours=1)
    session.add_all(
        [
            _call(video, {"input_tokens": 1_000_000}, created_at=created_at),
            _call(video, cost_usd=Decimal(1), error_code=LLM_CALL_IN_PROGRESS, created_at=now),
            _call(video, cost_usd=Decimal(2), error_code=LLM_CALL_TIMEOUT, created_at=now),
            _call(
                video,
                {"input_tokens": 1_000_000},
                LLMPurpose.EVAL,
                error_code="llm_refused",
                created_at=created_at,
            ),
        ]
    )
    await session.commit()

    [spend] = await quotas.llm_spend_by_day(session, 1, now=now)

    # A chamada em voo não é falha; a interrompida é, e as duas ficam sem resposta.
    assert (spend.calls, spend.failed_calls, spend.unfinished_calls) == (4, 2, 2)
    assert (spend.cost_usd, spend.eval_cost_usd) == (Decimal(4 + 1 + 2), Decimal(4))


async def test_spend_uses_cost_usd_and_falls_back_to_usage(session: AsyncSession) -> None:
    video = await make_video(session)
    usage = {"input_tokens": 1_000_000}  # US$ 4 pelo usage
    session.add_all([_call(video, usage, cost_usd=Decimal(1)), _call(video, usage)])
    await session.commit()

    assert await quotas.llm_spend_today(session) == Decimal(1 + 4)


async def test_in_progress_reservation_counts_in_budget(
    session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = await make_video(session)
    session.add(_call(video, error_code=LLM_CALL_IN_PROGRESS, cost_usd=Decimal(2)))
    await session.commit()

    assert await quotas.llm_spend_today(session) == Decimal(2)
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 2.0)
    assert not await quotas.llm_budget_available(session)


async def test_production_budget_ignores_eval_and_vice_versa(
    session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = await make_video(session)
    session.add_all(
        [
            _call(video, None, LLMPurpose.EVAL, cost_usd=Decimal(3)),
            _call(video, None, LLMPurpose.CLI, cost_usd=Decimal(1)),
            _call(video, None, LLMPurpose.DEFERRED, cost_usd=Decimal("0.5")),
        ]
    )
    await session.commit()
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 2.0)
    monkeypatch.setattr(settings, "eval_daily_llm_budget_usd", 3.0)

    assert await quotas.llm_spend_today(session) == Decimal("1.5")
    assert await quotas.llm_spend_today(session, quotas.Budget.EVAL) == Decimal(3)
    assert await quotas.llm_budget_available(session)
    with pytest.raises(LLMBudgetExceededError):
        await quotas.ensure_llm_budget(session, quotas.Budget.EVAL)


async def test_reservation_refuses_when_estimate_does_not_fit(
    session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 1.0)
    video = await make_video(session)
    session.add(_call(video, cost_usd=Decimal("0.5")))
    await session.commit()

    with pytest.raises(LLMBudgetExceededError) as exc_info:
        await quotas.reserve_llm_call(session, _call(video, cost_usd=Decimal("0.6")))

    assert "production" in (exc_info.value.detail or "")
    # A recusa termina a transação (libera o lock) sem expirar a sessão: o vídeo continua
    # legível sem lazy load.
    assert not session.in_transaction()
    assert video.youtube_id == "abcdefghijk"
    assert await session.scalar(select(func.count()).select_from(LLMCall)) == 1

    await quotas.reserve_llm_call(session, _call(video, cost_usd=Decimal("0.4")))

    assert await quotas.llm_spend_today(session) == Decimal("0.9")


async def test_concurrent_reservations_take_the_last_slack_once(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 1.5)
    video = await make_video(session)

    async def reserve() -> None:
        async with session_factory() as db:
            await quotas.reserve_llm_call(db, _call(video, cost_usd=Decimal(1)))

    results = await asyncio.gather(reserve(), reserve(), return_exceptions=True)

    assert sorted(type(result).__name__ for result in results) == [
        "LLMBudgetExceededError",
        "NoneType",
    ]
    assert await session.scalar(select(func.count()).select_from(LLMCall)) == 1


def test_cli_llm_spend_separates_production_and_eval(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = [quotas.DailySpend(date(2026, 5, 10), 4, 2, 2, Decimal(7), Decimal(4))]

    async def spend_by_day(session: Any, days: int) -> list[quotas.DailySpend]:
        return report

    class Engine:
        async def dispose(self) -> None:
            pass

    monkeypatch.setattr(cli, "llm_spend_by_day", spend_by_day)
    monkeypatch.setattr(cli, "SessionLocal", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(cli, "engine", Engine())
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 10.0)
    monkeypatch.setattr(settings, "eval_daily_llm_budget_usd", 5.0)

    assert cli.main(["llm-spend", "--days", "1"]) == 0

    out = capsys.readouterr().out
    assert "EVAL_DAILY_LLM_BUDGET_USD): US$ 5.00" in out
    assert "sem resposta" in out
    row = next(line for line in out.splitlines() if line.startswith("2026-05-10"))
    assert row.split() == ["2026-05-10", "4", "2", "2", "7.0000", "4.0000", "70%"]
    assert "produção US$ 7.0000, eval US$ 4.0000" in out
