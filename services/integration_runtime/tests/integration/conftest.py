import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from integration_runtime.adapters.s3_storage import S3Storage

APP_URL = os.environ.get(
    "INTEGRATION_DATABASE_URL",
    "postgresql+asyncpg://integration_app:integration_app_dev@localhost:55432/integration_runtime",
)


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(APP_URL)
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1 FROM integration.run_queue LIMIT 1"))
    except Exception as exc:  # pragma: no cover
        await eng.dispose()
        pytest.skip(f"Integration DB tayyor emas (make up && migratsiya): {exc}")
    yield eng
    await eng.dispose()


@pytest.fixture(scope="session")
async def storage() -> S3Storage:
    s = S3Storage(endpoint_url=os.environ.get("INTEGRATION_S3_ENDPOINT_URL", "http://localhost:9000"),
                  access_key="abo", secret_key="abo_dev_password")
    try:
        for bucket in ("abo-business", "abo-integration"):
            await s.ensure_bucket(bucket)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"S3 ombori tayyor emas: {exc}")
    return s
