import json
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.access import Visibility
from ..domain.spec import DashboardSpec
from ..ports.store import DashboardRecord, VersionInfo

_SELECT = (
    "SELECT d.id, d.current_version AS version, v.spec, d.created_by, d.updated_at,"
    " d.visibility, coalesce((SELECT array_agg(s.user_id) FROM dashboards.dashboard_shares s"
    "   WHERE s.dashboard_id = d.id), '{}') AS shared_with"
    " FROM dashboards.dashboards d JOIN dashboards.dashboard_versions v"
    " ON v.tenant_id = d.tenant_id AND v.dashboard_id = d.id AND v.version = d.current_version"
)


def _record(r: Any) -> DashboardRecord:
    return DashboardRecord(r.id, r.version, r.spec, r.created_by, r.updated_at,
                           Visibility(r.visibility), frozenset(r.shared_with))


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
        return None if r is None else _record(r)

    async def list_visible(self, *, limit: int, query: str | None, user_id: UUID,
                   see_all: bool) -> list[DashboardRecord]:
        rows = (await self._c.execute(text(
            _SELECT + " WHERE (CAST(:q AS text) IS NULL OR d.title ILIKE '%' || :q || '%')"
            " AND (:all OR d.created_by = :u OR d.visibility = 'tenant' OR EXISTS ("
            "   SELECT 1 FROM dashboards.dashboard_shares s WHERE s.dashboard_id = d.id"
            "   AND s.user_id = :u))"
            " ORDER BY d.updated_at DESC LIMIT :limit"),
            {"q": query, "limit": limit, "u": user_id, "all": see_all})).all()
        return [_record(r) for r in rows]

    async def add_version(self, dashboard_id: UUID, spec: DashboardSpec, *,
                          user_id: UUID) -> DashboardRecord:
        version: int = (await self._c.execute(text(
            "UPDATE dashboards.dashboards SET current_version = current_version + 1,"
            " title = :title, description = :desc, updated_at = now() WHERE id = :id"
            " RETURNING current_version"),
            {"id": dashboard_id, "title": spec.title, "desc": spec.description})).scalar_one()
        await self._c.execute(text(
            "INSERT INTO dashboards.dashboard_versions (tenant_id, dashboard_id, version, spec,"
            " created_by, created_at) VALUES (:t, :id, :v, CAST(:spec AS jsonb), :by, now())"),
            {"t": self._tenant, "id": dashboard_id, "v": version, "by": user_id,
             "spec": json.dumps(spec.to_json(), ensure_ascii=False)})
        record = await self.get(dashboard_id)
        assert record is not None
        return record

    async def versions(self, dashboard_id: UUID) -> list[VersionInfo]:
        rows = (await self._c.execute(text(
            "SELECT version, created_by, created_at, spec->>'title' AS title"
            " FROM dashboards.dashboard_versions WHERE dashboard_id = :id ORDER BY version DESC"),
            {"id": dashboard_id})).all()
        return [VersionInfo(r.version, r.created_by, r.created_at, r.title) for r in rows]

    async def set_access(self, dashboard_id: UUID, visibility: Visibility,
                         shared_with: frozenset[UUID], *, user_id: UUID) -> None:
        await self._c.execute(text(
            "UPDATE dashboards.dashboards SET visibility = :v, updated_at = now() WHERE id = :id"),
            {"v": visibility.value, "id": dashboard_id})
        await self._c.execute(text(
            "DELETE FROM dashboards.dashboard_shares WHERE dashboard_id = :id"),
            {"id": dashboard_id})
        if shared_with:
            await self._c.execute(text(
                "INSERT INTO dashboards.dashboard_shares (tenant_id, dashboard_id, user_id,"
                " created_by, created_at) VALUES (:t, :id, :u, :by, now())"),
                [{"t": self._tenant, "id": dashboard_id, "u": u, "by": user_id}
                 for u in shared_with])


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
