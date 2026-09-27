"""agent.agent_runs ↔ AgentRun mapping va tenant kontekstini bog‘lash."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.run import AgentRun, Checkpoint, RunStatus

COLUMNS = (
    "id, tenant_id, task_id, task_step_id, role_key, status, instruction, locale,"
    " capability_token, deadline, correlation_id, causation_id, max_tool_calls,"
    " tool_calls_used, cancel_requested, sequence, checkpoint"
)


async def bind_tenant(conn: AsyncConnection, tenant_id: UUID) -> None:
    """Faqat joriy tranzaksiya uchun (pool orqali sizib chiqmaydi)."""
    await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"),
                       {"t": str(tenant_id)})


def run_from_row(row: RowMapping) -> AgentRun:
    return AgentRun(
        id=row["id"],
        tenant_id=row["tenant_id"],
        task_id=row["task_id"],
        task_step_id=row["task_step_id"],
        role_key=row["role_key"],
        instruction=row["instruction"],
        locale=row["locale"],
        deadline=row["deadline"],
        capability_token=row["capability_token"],
        correlation_id=row["correlation_id"],
        causation_id=row["causation_id"],
        max_tool_calls=row["max_tool_calls"],
        status=RunStatus(row["status"]),
        tool_calls_used=row["tool_calls_used"],
        cancel_requested=row["cancel_requested"],
        sequence=row["sequence"],
        checkpoint=Checkpoint.from_json(row["checkpoint"]),
    )


def run_values(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id, "tenant_id": run.tenant_id, "task_id": run.task_id,
        "task_step_id": run.task_step_id, "role_key": run.role_key, "status": run.status.value,
        "instruction": run.instruction, "locale": run.locale,
        "capability_token": run.capability_token, "deadline": run.deadline,
        "correlation_id": run.correlation_id, "causation_id": run.causation_id,
        "max_tool_calls": run.max_tool_calls, "tool_calls_used": run.tool_calls_used,
        "cancel_requested": run.cancel_requested, "sequence": run.sequence,
    }
