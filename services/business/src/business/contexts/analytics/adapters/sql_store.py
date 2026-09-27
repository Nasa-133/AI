"""AnalyticsStore porti: joriy tranzaksiya va tenant kontekstiga bog‘langan PostgreSQL adapteri."""

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.ingestion import Entity
from ..ports.store import MetricSettings, SnapshotRef, StoredQuery
from .sql_ingest import SNAPSHOT_SELECT, SqlIngestion, snapshot_from_row
from .sql_query import SqlAggregates


class SqlAnalyticsStore(SqlIngestion, SqlAggregates):
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        SqlIngestion.__init__(self, conn, tenant_id)
        SqlAggregates.__init__(self, conn)

    async def active_snapshots(self) -> dict[Entity, SnapshotRef]:
        rows = (await self._c.execute(text(
            SNAPSHOT_SELECT + " WHERE d.is_active AND s.id = d.latest_snapshot_id"))).all()
        return {Entity(r.entity): snapshot_from_row(r) for r in rows}

    async def snapshots_by_ids(self, ids: list[UUID]) -> dict[Entity, SnapshotRef]:
        if not ids:
            return {}
        rows = (await self._c.execute(text(SNAPSHOT_SELECT + " WHERE s.id = ANY(:ids)"),
                                      {"ids": ids})).all()
        return {Entity(r.entity): snapshot_from_row(r) for r in rows}

    async def metric_settings(self) -> MetricSettings | None:
        r = (await self._c.execute(text(
            "SELECT version, settings, approved_by, approved_at FROM analytics.metric_settings"
            " ORDER BY version DESC LIMIT 1"))).first()
        return None if r is None else MetricSettings(r.version, r.settings, r.approved_by,
                                                     r.approved_at)

    async def save_metric_settings(self, settings: MetricSettings) -> None:
        await self._c.execute(text(
            "INSERT INTO analytics.metric_settings (tenant_id, version, settings, approved_by,"
            " approved_at) VALUES (:t, :v, CAST(:s AS jsonb), :by, :at)"),
            {"t": self._tenant, "v": settings.version, "s": json.dumps(settings.settings),
             "by": settings.approved_by, "at": settings.approved_at})

    async def save_query(self, query: StoredQuery) -> None:
        await self._c.execute(text(
            "INSERT INTO analytics.query_specs (tenant_id, id, kind, spec, snapshot_ids, result,"
            " created_by, task_id, created_at) VALUES (:t, :id, :k, CAST(:spec AS jsonb), :snaps,"
            " CAST(:res AS jsonb), :by, :task, now())"),
            {"t": self._tenant, "id": query.id, "k": query.kind,
             "spec": json.dumps(query.spec, ensure_ascii=False), "snaps": query.snapshot_ids,
             "res": json.dumps(query.result, ensure_ascii=False), "by": query.created_by,
             "task": query.task_id})

    async def get_query(self, query_id: UUID) -> StoredQuery | None:
        r = (await self._c.execute(text(
            "SELECT id, kind, spec, snapshot_ids, result, created_by, task_id, created_at"
            " FROM analytics.query_specs WHERE id = :id"), {"id": query_id})).first()
        if r is None:
            return None
        return StoredQuery(r.id, r.kind, r.spec, list(r.snapshot_ids), r.result, r.created_by,
                           r.task_id, r.created_at)
