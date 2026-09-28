import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class SqlIntegrationsStore:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._c = conn
        self._t = tenant_id

    async def add_upload(self, u: dict[str, Any]) -> None:
        await self._c.execute(text(
            "INSERT INTO integrations.uploads (tenant_id, id, purpose, filename, content_type,"
            " size_bytes, sha256, bucket, object_key, created_by, created_at, updated_at)"
            " VALUES (:t, :id, :purpose, :filename, :ct, :size, :sha, :bucket, :key, :by,"
            " now(), now())"), {"t": self._t, **u})

    async def get_upload(self, upload_id: UUID) -> dict[str, Any] | None:
        r = (await self._c.execute(text(
            "SELECT id, purpose, filename, size_bytes, sha256, bucket, object_key"
            " FROM integrations.uploads WHERE id = :id"), {"id": upload_id})).mappings().first()
        return None if r is None else dict(r)

    async def add_source(self, s: dict[str, Any]) -> None:
        await self._c.execute(text(
            "INSERT INTO integrations.data_sources (tenant_id, id, name, connector_id, upload_id,"
            " status, created_by, created_at, updated_at)"
            " VALUES (:t, :id, :name, :connector, :upload, :status, :by, now(), now())"),
            {"t": self._t, **s})

    async def get_source(self, source_id: UUID) -> dict[str, Any] | None:
        r = (await self._c.execute(text(
            "SELECT id, name, connector_id, upload_id, status, entity, discovery, mapping_version,"
            " last_sync_run_id, error_message, created_at, updated_at"
            " FROM integrations.data_sources WHERE id = :id FOR UPDATE"),
            {"id": source_id})).mappings().first()
        return None if r is None else dict(r)

    async def list_sources(self) -> list[dict[str, Any]]:
        rows = (await self._c.execute(text(
            "SELECT id, name, connector_id, status, entity, mapping_version, error_message,"
            " updated_at FROM integrations.data_sources ORDER BY updated_at DESC"))).mappings()
        return [dict(r) for r in rows.all()]

    async def update_source(self, source_id: UUID, **values: Any) -> None:
        allowed = {"status", "entity", "discovery", "mapping_version", "last_sync_run_id",
                   "error_message"}
        assert set(values) <= allowed
        sets = ", ".join(f"{k} = CAST(:{k} AS jsonb)" if k == "discovery" else f"{k} = :{k}"
                         for k in values)
        params = {k: _j(v) if k == "discovery" else v for k, v in values.items()}
        await self._c.execute(text(
            f"UPDATE integrations.data_sources SET {sets}, updated_at = now() WHERE id = :id"),  # noqa: S608 - ustun nomlari oq ro‘yxatdan
            {**params, "id": source_id})

    async def next_mapping_version(self, source_id: UUID) -> int:
        r = await self._c.execute(text(
            "SELECT coalesce(max(version), 0) + 1 FROM integrations.source_mappings"
            " WHERE data_source_id = :id"), {"id": source_id})
        return int(r.scalar_one())

    async def add_mapping(self, m: dict[str, Any]) -> None:
        await self._c.execute(text(
            "INSERT INTO integrations.source_mappings (tenant_id, data_source_id, version, entity,"
            " config, mapping, status, approved_by, approved_at) VALUES (:t, :source, :version,"
            " :entity, CAST(:config AS jsonb), CAST(:mapping AS jsonb), 'pending', :by, :at)"),
            {"t": self._t, **m, "config": _j(m["config"]), "mapping": _j(m["mapping"])})

    async def set_mapping_status(self, source_id: UUID, version: int, status: str,
                                 error: str | None) -> None:
        await self._c.execute(text(
            "UPDATE integrations.source_mappings SET status = :s, error_message = :e"
            " WHERE data_source_id = :id AND version = :v"),
            {"s": status, "e": error, "id": source_id, "v": version})

    async def add_sync_run(self, run: dict[str, Any]) -> None:
        await self._c.execute(text(
            "INSERT INTO integrations.sync_runs (tenant_id, id, data_source_id, mapping_version,"
            " status, requested_by, requested_at) VALUES (:t, :id, :source, :version,"
            " 'requested', :by, now())"), {"t": self._t, **run})

    async def find_same_source(self, source_id: UUID | None, connector_id: str, entity: str,
                               upload_sha256: str | None) -> dict[str, Any] | None:
        # Tashqi tizim — bir xil connector (bitta ulanish); fayl — bir xil tarkib (sha256).
        r = (await self._c.execute(text(
            "SELECT s.id, s.name FROM integrations.data_sources s"
            " LEFT JOIN integrations.uploads u ON u.tenant_id = s.tenant_id AND u.id = s.upload_id"
            " WHERE s.entity = :e AND s.connector_id = :c"
            " AND (CAST(:sha AS text) IS NULL OR trim(u.sha256) = :sha)"
            " AND (CAST(:id AS uuid) IS NULL OR s.id <> :id) LIMIT 1"),
            {"e": entity, "c": connector_id, "sha": upload_sha256, "id": source_id})).first()
        return None if r is None else {"id": r.id, "name": r.name}

    async def due_for_auto_sync(self, connectors: tuple[str, ...],
                                interval_seconds: int) -> list[dict[str, Any]]:
        rows = (await self._c.execute(text(
            "SELECT s.id, s.created_by FROM integrations.data_sources s"
            " LEFT JOIN integrations.sync_runs r"
            "   ON r.tenant_id = s.tenant_id AND r.id = s.last_sync_run_id"
            " WHERE s.connector_id = ANY(:c) AND s.mapping_version IS NOT NULL"
            "   AND s.status IN ('ready', 'synced', 'failed')"
            "   AND (r.requested_at IS NULL"
            "        OR r.requested_at < now() - make_interval(secs => :i))"
            " ORDER BY s.id"), {"c": list(connectors), "i": interval_seconds})).mappings()
        return [dict(r) for r in rows.all()]

    async def finish_sync_run(self, run_id: UUID, status: str, result: dict[str, Any]) -> None:
        await self._c.execute(text(
            "UPDATE integrations.sync_runs SET status = :s, result = CAST(:r AS jsonb),"
            " finished_at = now() WHERE id = :id"), {"s": status, "r": _j(result), "id": run_id})
