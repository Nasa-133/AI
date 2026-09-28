"""Haqiqiy PostgreSQL bilan testlar. Oldindan: `make up && make migrate`."""

import os
from collections.abc import AsyncIterator

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from business.bootstrap.app import create_app
from business.bootstrap.settings import Settings
from tests.unit.identity.fakes import RecordingNotifier

# Alohida test bazasi (scripts/test-dbs.sh): ishlayotgan stek bilan to‘qnashmaydi.
APP_URL = os.environ.get(
    "BUSINESS_TEST_DATABASE_URL",
    "postgresql+asyncpg://business_app:business_app_dev@localhost:55432/business_test",
)

pytestmark = pytest.mark.integration

TOOLS_TOKEN = "t" * 40
CAPABILITY_KEY = "k" * 40


@pytest.fixture(scope="session")
async def app_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(APP_URL)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM identity.users LIMIT 1"))
    except Exception as exc:  # pragma: no cover - muhitga bog‘liq
        await engine.dispose()
        pytest.skip(f"PostgreSQL tayyor emas (make up && make migrate): {exc}")
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture(scope="session")
async def client(
    app_engine: AsyncEngine, notifier: RecordingNotifier
) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        database_url=APP_URL,
        data_encryption_key=Fernet.generate_key().decode(),
        cookie_secure=False,
        tools_service_token=TOOLS_TOKEN,
        capability_signing_key=CAPABILITY_KEY,
        s3_access_key="abo",
        s3_secret_key="abo_dev_password",
    )
    app = create_app(settings, notifier=notifier)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await app.state.container.engine.dispose()
