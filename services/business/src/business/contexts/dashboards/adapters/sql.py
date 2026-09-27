import json
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.spec import DashboardSpec
from ..ports.store import DashboardRecord

_SELECT = (
    "SELECT d.id, d.current_version AS version, v.spec, d.created_by, d.updated_at"
    " FROM dashboards.dashboards d JOIN dashboards.dashboard_versions v"
    " ON v.tenant_id = d.tenant_id AND v.dashboard_id = d.id AND v.version = d.current_version"
)


class SqlDashboardStore:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._c = conn
        self._tenant = tenant_id

    async def create(self, dashboard_id: UUID, spec: DashboardSpec, *, user_id: UUID,
                     task_id: UUID | None) -> DashboardRecord:
        params = {"t": self._tenant, "id": dashboard_id, "title": spec.title,
                  "desc": spec.description, "by": user_id, "task": task_id,
                  "spec": json.dumps(spec.to_json(), ensure_ascii=False)}
        await self._c.execute(text(
            "INSERT INTO dashboards.dashboards (tenant_id, id, title, description, current_version,"
            " created_by, created_task_id, created_at, updated_at)"
            " VALUES (:t, :id, :title, :desc, 1, :by, :task, now(), now())"), params)
        await self._c.execute(text(
            "INSERT INTO dashboards.dashboard_versions (tenant_id, dashboard_id, version, spec,"
            " created_by, created_at) VALUES (:t, :id, 1, CAST(:spec AS jsonb), :by, now())"),
            params)
        record = await self.get(dashboard_id)
        assert record is not None
        return record

    async def get(self, dashboard_id: UUID) -> DashboardRecord | None:
        r = (await self._c.execute(text(_SELECT + " WHERE d.id = :id"),
                                   {"id": dashboard_id})).first()
        return None if r is None else DashboardRecord(r.id, r.version, r.spec, r.created_by,
                                                      r.updated_at)

    async def list(self, *, limit: int, query: str | None) -> list[DashboardRecord]:
        rows = (await self._c.execute(text(
            _SELECT + " WHERE (CAST(:q AS text) IS NULL OR d.title ILIKE '%' || :q || '%')"
            " ORDER BY d.updated_at DESC LIMIT :limit"), {"q": query, "limit": limit})).all()
        return [DashboardRecord(r.id, r.version, r.spec, r.created_by, r.updated_at)
                for r in rows]


class QueryReaderLike(Protocol):
    async def get_query(self, query_id: UUID) -> Any: ...


class AnalyticsQueryResults:
    """QueryResults porti Analytics public API’si ustida."""

    def __init__(self, reader: QueryReaderLike) -> None:
        self._reader = reader

    async def result(self, query_id: UUID) -> dict[str, Any] | None:
        stored = await self._reader.get_query(query_id)
        return None if stored is None else dict(stored.result)

    async def spec(self, query_id: UUID) -> dict[str, Any] | None:
        stored = await self._reader.get_query(query_id)
        if stored is None or stored.kind != "query":
            return None
        return dict(stored.spec)
