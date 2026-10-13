import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.db import Base

FIXTURES = Path(__file__).parent / "fixtures"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://receita:receita@localhost:5432/receita_test"
)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Sessão num banco de teste com o schema recriado do zero a cada teste."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except (OSError, ConnectionError) as exc:
        await engine.dispose()
        pytest.skip(f"banco de teste indisponível ({TEST_DATABASE_URL}): {exc}")

    async with async_sessionmaker(engine, expire_on_commit=False)() as db_session:
        yield db_session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
