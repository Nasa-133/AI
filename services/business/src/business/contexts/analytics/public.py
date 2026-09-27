"""Analytics ochiq API’si: boshqa kontekstlar saqlangan query natijalarini shu orqali o‘qiydi."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from .adapters.sql_store import SqlAnalyticsStore
from .ports.store import StoredQuery


class QueryReader(Protocol):
    async def get_query(self, query_id: UUID) -> StoredQuery | None: ...


def query_reader(conn: AsyncConnection, tenant_id: UUID) -> QueryReader:
    return SqlAnalyticsStore(conn, tenant_id)


__all__ = ["QueryReader", "StoredQuery", "query_reader"]
