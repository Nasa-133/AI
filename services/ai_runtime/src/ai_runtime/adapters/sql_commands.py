"""RunCommands: consumer tranzaksiyasi ichida (tenant konteksti allaqachon bog‘langan)."""

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.run import AgentRun
from .sql_rows import run_values


class SqlRunCommands:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create_if_absent(self, run: AgentRun) -> bool:
        values = run_values(run)
        values["checkpoint"] = json.dumps(run.checkpoint.to_json())
        inserted = await self._conn.execute(text(
            "INSERT INTO agent.agent_runs (id, tenant_id, task_id, task_step_id, role_key, status,"
            " instruction, locale, capability_token, deadline, correlation_id, causation_id,"
            " max_tool_calls, tool_calls_used, cancel_requested, sequence, checkpoint)"
            " VALUES (:id, :tenant_id, :task_id, :task_step_id, :role_key, :status, :instruction,"
            " :locale, :capability_token, :deadline, :correlation_id, :causation_id,"
            " :max_tool_calls, :tool_calls_used, :cancel_requested, :sequence,"
            " CAST(:checkpoint AS jsonb))"
            " ON CONFLICT (task_step_id) DO NOTHING RETURNING id"), values)
        if inserted.first() is None:
            return False
        await self._conn.execute(text(
            "INSERT INTO agent.run_queue (run_id, tenant_id) VALUES (:id, :t)"),
            {"id": run.id, "t": run.tenant_id})
        return True

    async def request_cancel(self, task_step_id: UUID) -> bool:
        result = await self._conn.execute(text(
            "UPDATE agent.agent_runs SET cancel_requested = true, updated_at = now()"
            " WHERE task_step_id = :s AND status IN ('queued', 'running') RETURNING id"),
            {"s": task_step_id})
        return result.first() is not None
