"""Analytics ochiq API’si: boshqa kontekstlar saqlangan query natijalarini shu orqali o‘qiydi."""

from datetime import date
from typing import Any, Protocol
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
                 timezone: str, branch_scope: tuple[str, ...] | None = None) -> None:
        self._service = QueryService(SqlAnalyticsStore(conn, tenant_id))
        self._ctx = QueryContext(user_id, None, today, timezone, branch_scope)

    async def rerun(self, query_id: UUID) -> UUID | None:
        return await rerun_stored(self._service, self._ctx, query_id)


class SourceDatasets:
    """Integratsiyalar sahifasi uchun: har manba hisobga olinadimi (takroriy baza emasmi) va
    foydalanuvchi tanlovi bilan qaysi manba ishlatilishi."""

    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._s = SqlAnalyticsStore(conn, tenant_id)

    async def status(self) -> dict[UUID, list[dict[str, Any]]]:
        out: dict[UUID, list[dict[str, Any]]] = {}
        for r in await self._s.source_status():
            out.setdefault(r["data_source_id"], []).append(r)
        return out

    async def use(self, data_source_id: UUID) -> list[UUID]:
        return await self._s.activate_source(data_source_id)


__all__ = ["QueryReader", "SourceDatasets", "StoredQuery", "StoredQueryRefresher",
           "query_reader"]
