import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from abo_messaging.store import OUTBOX_INBOX_DDL

ADMIN_URL = os.environ.get(
    "ABO_TEST_ADMIN_DATABASE_URL", "postgresql+asyncpg://postgres:postgres_dev@localhost:55432/postgres"
)
TEST_DB = "abo_messaging_test"


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = (await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": TEST_DB})).first()
            if not exists:
                await conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    except Exception as exc:  # pragma: no cover - muhitga bog‘liq
        pytest.skip(f"PostgreSQL tayyor emas: {exc}")
    finally:
        await admin.dispose()
    eng = create_async_engine(ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}")
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncEngine:
    async with engine.connect() as conn, conn.begin():
        await conn.execute(text("DROP SCHEMA IF EXISTS messaging CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS public.effects"))
        for statement in OUTBOX_INBOX_DDL.split(";"):
            if statement.strip():
                await conn.execute(text(statement))
        await conn.execute(text("CREATE TABLE public.effects (event_id uuid, note text)"))
    return engine
