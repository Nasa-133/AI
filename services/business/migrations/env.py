import asyncio
import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# `helpers/rls.py` migratsiyalardan import qilinadi (versions/ ichida bo‘lsa alembic uni revision deb o‘qiydi).
sys.path.insert(0, str(Path(__file__).parent / "helpers"))


def _url() -> str:
    url = os.environ.get("BUSINESS_MIGRATIONS_DATABASE_URL")
    if not url:
        raise RuntimeError("BUSINESS_MIGRATIONS_DATABASE_URL o‘rnatilmagan")
    return url


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
