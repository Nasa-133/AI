"""Analytics ochiq API’si: boshqa kontekstlar saqlangan query natijalarini shu orqali o‘qiydi."""

from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from .adapters.sql_store import SqlAnalyticsStore
from .application.queries import QueryContext, QueryService, rerun_stored
from .ports.store import StoredQuery


class QueryReader(Protocol):
    async def get_query(self, query_id: UUID) -> StoredQuery | None: ...


def query_reader(conn: AsyncConnection, tenant_id: UUID) -> QueryReader:
    return SqlAnalyticsStore(conn, tenant_id)


class StoredQueryRefresher:
    """Dashboards konteksti uchun: saqlangan so‘rovni oxirgi snapshot bilan qayta hisoblaydi."""

    def __init__(self, conn: AsyncConnection, tenant_id: UUID, *, user_id: UUID, today: date,
                 timezone: str) -> None:
        self._service = QueryService(SqlAnalyticsStore(conn, tenant_id))
        self._ctx = QueryContext(user_id, None, today, timezone)

    async def rerun(self, query_id: UUID) -> UUID | None:
        return await rerun_stored(self._service, self._ctx, query_id)


__all__ = ["QueryReader", "StoredQuery", "StoredQueryRefresher", "query_reader"]
