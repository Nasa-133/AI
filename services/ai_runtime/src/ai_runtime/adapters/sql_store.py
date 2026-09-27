"""RunStore: lease bilan run olish, checkpoint va outbox eventlarini atomar saqlash."""

import json
from datetime import timedelta

from abo_messaging import enqueue, new_envelope
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ..domain.run import AgentRun
from ..ports.store import LeaseLost, PendingEvent
from .sql_rows import COLUMNS, bind_tenant, run_from_row


class SqlRunStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim(self, owner: str, lease: timedelta) -> AgentRun | None:
        async with self._engine.connect() as conn, conn.begin():
            # Navbatda faqat ID’lar: tenant kontekstisiz o‘qish xavfsiz (migratsiya 0001).
            row = (await conn.execute(text(
                "SELECT run_id, tenant_id FROM agent.run_queue"
                " WHERE lease_expires_at IS NULL OR lease_expires_at < now()"
                " ORDER BY enqueued_at LIMIT 1 FOR UPDATE SKIP LOCKED"))).first()
            if row is None:
                return None
            await conn.execute(text(
                "UPDATE agent.run_queue SET lease_owner = :o, lease_expires_at = now() + :l"
                " WHERE run_id = :id"), {"o": owner, "l": lease, "id": row.run_id})
            await bind_tenant(conn, row.tenant_id)
            found = (await conn.execute(
                text(f"SELECT {COLUMNS} FROM agent.agent_runs WHERE id = :id"),  # noqa: S608
                {"id": row.run_id})).mappings().first()
            if found is None:  # pragma: no cover - FK kafolatlaydi
                return None
            return run_from_row(found)

    async def refresh_cancel(self, run: AgentRun) -> bool:
        async with self._engine.connect() as conn, conn.begin():
            await bind_tenant(conn, run.tenant_id)
            value = (await conn.execute(text(
                "SELECT cancel_requested FROM agent.agent_runs WHERE id = :id"),
                {"id": run.id})).scalar()
        run.cancel_requested = bool(value)
        return run.cancel_requested

    async def commit_step(self, run: AgentRun, owner: str, lease: timedelta,
                          events: list[PendingEvent]) -> None:
        async with self._engine.connect() as conn, conn.begin():
            held = (await conn.execute(text(
                "UPDATE agent.run_queue SET lease_expires_at = now() + :l"
                " WHERE run_id = :id AND lease_owner = :o RETURNING run_id"),
                {"l": lease, "id": run.id, "o": owner})).first()
            if held is None:
                raise LeaseLost(str(run.id))
            await bind_tenant(conn, run.tenant_id)
            await conn.execute(text(
                "UPDATE agent.agent_runs SET status = :status, tool_calls_used = :used,"
                " sequence = :seq, checkpoint = CAST(:cp AS jsonb), updated_at = now()"
                " WHERE id = :id"),
                {"status": run.status.value, "used": run.tool_calls_used, "seq": run.sequence,
                 "cp": json.dumps(run.checkpoint.to_json(), ensure_ascii=False), "id": run.id})
            for event in events:
                await enqueue(conn, new_envelope(
                    event_type=event.event_type, producer="ai_runtime",
                    tenant_id=run.tenant_id, aggregate_id=run.id,
                    aggregate_version=event.aggregate_version, payload=event.payload,
                    correlation_id=run.correlation_id, causation_id=run.causation_id))
            if run.status.is_final:
                await conn.execute(text("DELETE FROM agent.run_queue WHERE run_id = :id"),
                                   {"id": run.id})
