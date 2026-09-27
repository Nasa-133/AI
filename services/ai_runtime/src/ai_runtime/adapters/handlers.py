"""Broker handler’lari (navbat `ai_runtime.agent`): envelope → application command."""

from datetime import datetime
from uuid import UUID

from abo_messaging import Envelope, Handler, PermanentError
from sqlalchemy.ext.asyncio import AsyncConnection

from ..application.commands import RunAgentCommand, accept_run, cancel_run
from .sql_commands import SqlRunCommands
from .sql_rows import bind_tenant

QUEUE = "ai_runtime.agent"


async def bind_envelope_tenant(conn: AsyncConnection, envelope: Envelope) -> None:
    await bind_tenant(conn, envelope.tenant_id)


def make_handlers(*, max_tool_calls: int) -> dict[str, Handler]:
    async def run_agent(conn: AsyncConnection, envelope: Envelope) -> None:
        p = envelope.payload
        try:
            cmd = RunAgentCommand(
                tenant_id=envelope.tenant_id,
                task_id=UUID(p["task_id"]),
                task_step_id=UUID(p["task_step_id"]),
                role_key=str(p["agent_role_key"]),
                instruction=str(p["sanitized_instruction"]),
                locale=str(p["locale"]),
                deadline=datetime.fromisoformat(p["deadline"]),
                capability_token=str(p["capability_token"]),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.event_id,
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise PermanentError(f"RunAgent payload noto‘g‘ri: {exc}") from exc
        await accept_run(SqlRunCommands(conn), cmd, max_tool_calls=max_tool_calls)

    async def cancel_agent_run(conn: AsyncConnection, envelope: Envelope) -> None:
        try:
            step = UUID(envelope.payload["task_step_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise PermanentError(f"CancelAgentRun payload noto‘g‘ri: {exc}") from exc
        await cancel_run(SqlRunCommands(conn), step)

    return {"RunAgent.v1": run_agent, "CancelAgentRun.v1": cancel_agent_run}
