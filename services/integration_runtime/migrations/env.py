import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine


def _url() -> str:
    return os.environ.get(
        "INTEGRATION_MIGRATIONS_DATABASE_URL",
        "postgresql+asyncpg://integration_owner:integration_owner_dev@localhost:55432/integration_runtime",
    )


def _run(connection: Connection) -> None:
    context.configure(connection=connection, version_table_schema="public")
    with context.begin_transaction():
        context.run_migrations()


async def _main() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


asyncio.run(_main())
