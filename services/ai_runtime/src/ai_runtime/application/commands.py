"""Broker command’lari: RunAgent va CancelAgentRun (consumer tranzaksiyasi ichida, tez)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from ..domain.run import AgentRun
from ..ports.store import RunCommands


@dataclass(frozen=True, slots=True)
class RunAgentCommand:
    tenant_id: UUID
    task_id: UUID
    task_step_id: UUID
    role_key: str
    instruction: str
    locale: str
    deadline: datetime
    capability_token: str
    correlation_id: UUID
    causation_id: UUID


async def accept_run(commands: RunCommands, cmd: RunAgentCommand, *, max_tool_calls: int) -> bool:
    """Idempotent: bir task_step uchun faqat bitta run. Og‘ir ish runner’da."""
    run = AgentRun(
        id=uuid4(),
        tenant_id=cmd.tenant_id,
        task_id=cmd.task_id,
        task_step_id=cmd.task_step_id,
        role_key=cmd.role_key,
        instruction=cmd.instruction,
        locale=cmd.locale,
        deadline=cmd.deadline,
        capability_token=cmd.capability_token,
        correlation_id=cmd.correlation_id,
        causation_id=cmd.causation_id,
        max_tool_calls=max_tool_calls,
    )
    return await commands.create_if_absent(run)


async def cancel_run(commands: RunCommands, task_step_id: UUID) -> bool:
    return await commands.request_cancel(task_step_id)
