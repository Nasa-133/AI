import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


class SqlAuditLog:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._c = conn
        self._t = tenant_id

    async def record(self, *, actor_id: UUID | None, actor_kind: str, action: str,
                     target_type: str | None, target_id: str | None,
                     details: dict[str, Any], ip: str | None) -> None:
        await self._c.execute(text(
            "INSERT INTO governance.audit_events (tenant_id, actor_id, actor_kind, action,"
            " target_type, target_id, details, ip, created_at)"
            " VALUES (:t, :a, :k, :act, :tt, :tid, CAST(:d AS jsonb), :ip, clock_timestamp())"),
            {"t": self._t, "a": actor_id, "k": actor_kind, "act": action, "tt": target_type,
             "tid": target_id, "d": json.dumps(details, ensure_ascii=False, default=str),
             "ip": ip})

    async def recent(self, limit: int, before_id: int | None) -> list[dict[str, Any]]:
        rows = (await self._c.execute(text(
            "SELECT id, actor_id, actor_kind, action, target_type, target_id, details, ip,"
            " created_at FROM governance.audit_events"
            " WHERE (CAST(:b AS bigint) IS NULL OR id < :b) ORDER BY id DESC LIMIT :n"),
            {"b": before_id, "n": limit})).mappings().all()
        return [dict(r) for r in rows]

    async def purge(self, keep_days: int) -> int:
        r = await self._c.execute(text("SELECT governance.purge_audit(:d)"), {"d": keep_days})
        return int(r.scalar_one())
