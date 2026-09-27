"""PostgreSQL repository (integration schema). Tenant jadvallari RLS ostida; run_queue — yo‘q."""

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.batch import RejectionReport
from ..domain.mapping import SourceMapping
from ..ports.repository import BatchRecord, ClaimedRun, MessageContext, SyncRun
from .sql_codec import mapping_from_json, mapping_to_json, ref_from_json, ref_to_json


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class SqlIntegrationRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._c = conn

    async def ensure_data_source(self, tenant_id: UUID, data_source_id: UUID,
                                 connector_id: str) -> str:
        await self._c.execute(text(
            "INSERT INTO integration.data_sources (tenant_id, id, connector_id)"
            " VALUES (:t, :id, :c) ON CONFLICT (tenant_id, id) DO NOTHING"),
            {"t": tenant_id, "id": data_source_id, "c": connector_id})
        row = (await self._c.execute(text(
            "SELECT connector_id FROM integration.data_sources WHERE id = :id"),
            {"id": data_source_id})).one()
        return str(row.connector_id)

    async def get_mapping(self, data_source_id: UUID, version: int) -> SourceMapping | None:
        row = (await self._c.execute(text(
            "SELECT entity, config, mapping FROM integration.source_mappings"
            " WHERE data_source_id = :d AND version = :v"),
            {"d": data_source_id, "v": version})).first()
        return None if row is None else mapping_from_json(row.entity, row.config, row.mapping)

    async def add_mapping(self, *, tenant_id: UUID, data_source_id: UUID, version: int,
                          mapping: SourceMapping, approved_by: UUID,
                          approved_at: datetime) -> None:
        config, items = mapping_to_json(mapping)
        await self._c.execute(text(
            "INSERT INTO integration.source_mappings (tenant_id, data_source_id, version, entity,"
            " config, mapping, approved_by, approved_at) VALUES (:t, :d, :v, :e,"
            " CAST(:c AS jsonb), CAST(:m AS jsonb), :by, :at)"),
            {"t": tenant_id, "d": data_source_id, "v": version, "e": mapping.entity,
             "c": _j(config), "m": _j(items), "by": approved_by, "at": approved_at})

    async def add_sync_run(self, run: SyncRun) -> bool:
        result = await self._c.execute(text(
            "INSERT INTO integration.sync_runs (tenant_id, id, data_source_id, connector_id, mode,"
            " mapping_version, object_ref, requested_by, status, correlation_id, causation_id,"
            " traceparent) VALUES (:t, :id, :d, :c, :mode, :v, CAST(:ref AS jsonb), :by,"
            " :status, :corr, :cause, :tp) ON CONFLICT (id) DO NOTHING RETURNING id"),
            {"t": run.tenant_id, "id": run.id, "d": run.data_source_id, "c": run.connector_id,
             "mode": run.mode, "v": run.mapping_version, "ref": _j(ref_to_json(run.object_ref)),
             "by": run.requested_by, "status": run.status,
             "corr": run.context.correlation_id, "cause": run.context.causation_id,
             "tp": run.context.traceparent})
        return result.first() is not None

    async def get_sync_run(self, sync_run_id: UUID) -> SyncRun | None:
        r = (await self._c.execute(text(
            "SELECT * FROM integration.sync_runs WHERE id = :id"), {"id": sync_run_id})).first()
        if r is None:
            return None
        return SyncRun(
            id=r.id, tenant_id=r.tenant_id, data_source_id=r.data_source_id,
            connector_id=r.connector_id, mode=r.mode, mapping_version=r.mapping_version,
            object_ref=ref_from_json(r.object_ref), requested_by=r.requested_by, status=r.status,
            context=MessageContext(r.tenant_id, r.correlation_id, r.causation_id, r.traceparent),
        )

    async def mark_running(self, sync_run_id: UUID) -> None:
        await self._c.execute(text(
            "UPDATE integration.sync_runs SET status = 'running', updated_at = now()"
            " WHERE id = :id"), {"id": sync_run_id})

    async def finish_sync_run(self, sync_run_id: UUID, *, status: str, record_count: int,
                              rejections: RejectionReport, error_code: str | None) -> None:
        samples = [{"row_number": s.row_number, "source_id": s.source_id, "reason": s.reason}
                   for s in rejections.samples]
        await self._c.execute(text(
            "UPDATE integration.sync_runs SET status = :s, record_count = :n,"
            " rejected_count = :rc, rejection_samples = CAST(:rs AS jsonb), error_code = :e,"
            " finished_at = now(), updated_at = now() WHERE id = :id"),
            {"s": status, "n": record_count, "rc": rejections.count, "rs": _j(samples),
             "e": error_code, "id": sync_run_id})

    async def insert_batch(self, batch: BatchRecord) -> bool:
        result = await self._c.execute(text(
            "INSERT INTO integration.batches (tenant_id, id, sync_run_id, data_source_id,"
            " connector_id, connector_version, entity, canonical_schema_version, record_count,"
            " object_ref, extracted_at, is_full_snapshot) VALUES (:t, :id, :run, :d, :c, :cv,"
            " :e, :sv, :n, CAST(:ref AS jsonb), :at, :full)"
            " ON CONFLICT (sync_run_id, entity) DO NOTHING RETURNING id"),
            {"t": batch.tenant_id, "id": batch.id, "run": batch.sync_run_id,
             "d": batch.data_source_id, "c": batch.connector_id, "cv": batch.connector_version,
             "e": batch.entity, "sv": batch.canonical_schema_version, "n": batch.record_count,
             "ref": _j(ref_to_json(batch.object_ref)), "at": batch.extracted_at,
             "full": batch.is_full_snapshot})
        return result.first() is not None

    # --- lease navbati (RLS’siz, faqat ID) ---
    async def enqueue_run(self, sync_run_id: UUID, tenant_id: UUID) -> None:
        await self._c.execute(text(
            "INSERT INTO integration.run_queue (sync_run_id, tenant_id) VALUES (:id, :t)"
            " ON CONFLICT DO NOTHING"), {"id": sync_run_id, "t": tenant_id})

    async def claim_run(self, owner: str, lease: timedelta) -> ClaimedRun | None:
        row = (await self._c.execute(text(
            "UPDATE integration.run_queue SET lease_owner = :o, attempts = attempts + 1,"
            " lease_expires_at = now() + :lease WHERE sync_run_id = ("
            "  SELECT sync_run_id FROM integration.run_queue WHERE available_at <= now()"
            "  AND (lease_expires_at IS NULL OR lease_expires_at < now())"
            "  ORDER BY available_at FOR UPDATE SKIP LOCKED LIMIT 1)"
            " RETURNING sync_run_id, tenant_id, attempts"), {"o": owner, "lease": lease})).first()
        return None if row is None else ClaimedRun(row.sync_run_id, row.tenant_id, row.attempts)

    async def extend_lease(self, sync_run_id: UUID, owner: str, lease: timedelta) -> None:
        await self._c.execute(text(
            "UPDATE integration.run_queue SET lease_expires_at = now() + :lease"
            " WHERE sync_run_id = :id AND lease_owner = :o"),
            {"lease": lease, "id": sync_run_id, "o": owner})

    async def release_run(self, sync_run_id: UUID, delay: timedelta) -> None:
        await self._c.execute(text(
            "UPDATE integration.run_queue SET lease_owner = NULL, lease_expires_at = NULL,"
            " available_at = now() + :delay WHERE sync_run_id = :id"),
            {"delay": delay, "id": sync_run_id})

    async def complete_run(self, sync_run_id: UUID) -> None:
        await self._c.execute(text("DELETE FROM integration.run_queue WHERE sync_run_id = :id"),
                              {"id": sync_run_id})
