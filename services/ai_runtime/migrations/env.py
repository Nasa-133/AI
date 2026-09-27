import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

DEFAULT_URL = "postgresql+asyncpg://ai_owner:ai_owner_dev@localhost:55432/ai_runtime"


def _run(connection: Connection) -> None:
    context.configure(connection=connection, version_table_schema="public")
    with context.begin_transaction():
        context.run_migrations()


async def _main() -> None:
    engine = create_async_engine(os.environ.get("AI_MIGRATIONS_DATABASE_URL", DEFAULT_URL))
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


asyncio.run(_main())
