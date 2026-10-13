import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from arq.connections import ArqRedis, RedisSettings
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app import queue
from app.api.deps import get_redis
from app.config import Settings, get_settings
from app.db import Base, get_session
from app.main import app as fastapi_app
from app.services import email as email_service
from app.services.email import Email

FIXTURES = Path(__file__).parent / "fixtures"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://receita:receita@localhost:5432/receita_test"
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture
def settings() -> Settings:
    """As settings do app; mude com `monkeypatch.setattr(settings, ...)` (desfeito no fim)."""
    return get_settings()


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[Email]:
    """E-mails enviados durante o teste, no lugar do backend configurado."""
    sent: list[Email] = []

    async def send(message: Email) -> None:
        sent.append(message)

    monkeypatch.setattr(email_service, "send", send)
    return sent


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """Banco de teste com o schema recriado do zero a cada teste."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except (OSError, ConnectionError) as exc:
        await engine.dispose()
        pytest.skip(f"banco de teste indisponível ({TEST_DATABASE_URL}): {exc}")

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as db_session:
        yield db_session


@pytest.fixture
async def redis() -> AsyncIterator[ArqRedis]:
    """Redis de teste (db 15 por padrão), esvaziado antes e depois de cada teste."""
    settings = RedisSettings.from_dsn(TEST_REDIS_URL)
    settings.conn_retries = 0
    try:
        pool = await queue.create_redis_pool(settings)
        await pool.flushdb()
    except (OSError, RedisError) as exc:
        pytest.skip(f"redis de teste indisponível ({TEST_REDIS_URL}): {exc}")

    yield pool

    await pool.flushdb()
    await pool.aclose()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession], redis: ArqRedis
) -> AsyncIterator[AsyncClient]:
    async def test_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as db_session:
            yield db_session

    fastapi_app.dependency_overrides[get_session] = test_session
    fastapi_app.dependency_overrides[get_redis] = lambda: redis
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    fastapi_app.dependency_overrides.clear()
