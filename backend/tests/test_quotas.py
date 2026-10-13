"""Cota diária de receitas novas por usuário e custo/orçamento do Claude."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from arq.connections import ArqRedis
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import queue
from app.config import Settings
from app.models import Import, ImportStatus, LLMCall, User
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

    assert quotas.llm_cost_usd("modelo-novo", usage) == Decimal(30)


async def test_spend_today_ignores_previous_days(session: AsyncSession) -> None:
    video = await make_video(session)
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    session.add_all(
        [
            LLMCall(video_id=video.id, model="claude-opus-5-5", prompt_version="v", usage=usage),
            LLMCall(
                video_id=video.id,
                model="claude-opus-5-5",
                prompt_version="v",
                usage=usage,
                error_code="llm_refused",
            ),
            LLMCall(
                video_id=video.id,
                model="claude-opus-5-5",
                prompt_version="v",
                usage=usage,
                created_at=datetime.now(UTC) - timedelta(days=1),
            ),
        ]
    )
    await session.commit()

    assert await quotas.llm_spend_today(session) == Decimal(8)


async def test_budget_check(
    session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = await make_video(session)
    session.add(
        LLMCall(
            video_id=video.id,
            model="claude-opus-5-5",
            prompt_version="v",
            usage={"input_tokens": 0, "output_tokens": 100_000},  # US$ 2
        )
    )
    await session.commit()

    monkeypatch.setattr(settings, "daily_llm_budget_usd", 2.5)
    assert await quotas.llm_budget_available(session)
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
        return LLMCall(
            video_id=video.id,
            model="claude-opus-5-5",
            prompt_version="v",
            usage=usage,
            error_code=error_code,
            created_at=created_at,
        )

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

    assert [(s.day.isoformat(), s.calls, s.failed_calls, s.cost_usd) for s in report] == [
        ("2026-05-10", 2, 1, Decimal(8)),
        ("2026-05-09", 0, 0, Decimal(0)),
        ("2026-05-08", 1, 0, Decimal(4)),
    ]
