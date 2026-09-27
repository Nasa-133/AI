"""Haqiqiy PostgreSQL (ai_runtime DB, ai_app roli).

Oldindan: make up; uv run alembic upgrade head.
"""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

APP_URL = os.environ.get(
    "AI_DATABASE_URL", "postgresql+asyncpg://ai_app:ai_app_dev@localhost:55432/ai_runtime")


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(APP_URL)
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1 FROM agent.run_queue LIMIT 1"))
    except Exception as exc:  # pragma: no cover - muhitga bog‘liq
        await eng.dispose()
        pytest.skip(f"AI DB tayyor emas (alembic upgrade head): {exc}")
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncEngine:
    """Har test bo‘sh navbatdan boshlanadi (boshqa testlar run’larini olmaslik uchun)."""
    async with engine.connect() as conn, conn.begin():
        await conn.execute(text("DELETE FROM agent.run_queue"))
    return engine
