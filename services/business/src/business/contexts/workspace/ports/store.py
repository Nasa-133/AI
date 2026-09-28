from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TaskView:
    id: UUID
    conversation_id: UUID
    initiator_id: UUID
    agent_role_key: str
    status: str
    cancel_requested: bool
    error_code: str | None
    limitations: list[str]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StepView:
    id: UUID
    task_id: UUID
    agent_role_key: str
    status: str
    phase: str | None
    progress_seq: int


@dataclass(frozen=True, slots=True)
class QueuedTask:
    task_id: UUID
    step_id: UUID
    initiator_id: UUID
    dispatch: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AgentTaskRow:
    """Ofis uchun: agentga bog‘langan vazifa, uning qadami va navbat ma’lumoti."""

    task_id: UUID
    conversation_id: UUID
    initiator_id: UUID
    agent_role_key: str
    title: str
    status: str
    error_code: str | None
    dispatched: bool
    step_status: str
    step_kind: str
    step_phase: str | None
    wait_reason: str | None
    answered: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TaskEvent:
    id: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class WorkspaceStore(Protocol):
    async def create_conversation(self, conversation_id: UUID, title: str,
                                  user_id: UUID) -> None: ...
    async def conversation_exists(self, conversation_id: UUID) -> bool: ...
    async def list_conversations(self, user_id: UUID, limit: int) -> list[dict[str, Any]]: ...
    async def list_messages(self, conversation_id: UUID, limit: int) -> list[dict[str, Any]]: ...
    async def add_message(self, message: dict[str, Any]) -> None: ...
    async def create_task(self, task_id: UUID, conversation_id: UUID, user_id: UUID,
                          role: str, step_id: UUID, *, title: str,
                          dispatch: dict[str, Any]) -> None: ...
    async def get_task(self, task_id: UUID) -> TaskView | None: ...
    async def get_step(self, step_id: UUID) -> StepView | None: ...
    async def list_steps(self, task_id: UUID) -> list[StepView]: ...
    async def set_task(self, task_id: UUID, *, status: str | None = None,
                       cancel_requested: bool | None = None, error_code: str | None = None,
                       limitations: list[str] | None = None) -> None: ...
    async def set_step(self, step_id: UUID, *, status: str, phase: str | None,
                       progress_seq: int | None, agent_run_id: UUID | None,
                       kind: str | None = None) -> None: ...
    # --- agent navbati ---
    async def lock_agent(self, role: str) -> None: ...
    async def count_active(self, role: str) -> int: ...
    async def waiting(self, role: str) -> list[QueuedTask]: ...
    async def mark_dispatched(self, task_id: UUID) -> None: ...
    async def is_dispatched(self, task_id: UUID) -> bool: ...
    async def queue_position(self, task_id: UUID) -> int | None: ...
    async def agent_tasks(self, since_seconds: int) -> list[AgentTaskRow]: ...
    async def list_tasks(self, user_id: UUID, limit: int) -> list[AgentTaskRow]: ...
    # --- fon ishlari ---
    async def stuck_tasks(self, older_than_seconds: int) -> list[TaskView]: ...
    async def purge_conversations(self, *, days: int) -> int: ...
    async def purge_idempotency_keys(self, *, days: int) -> int: ...
    async def answers(self, task_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
        """Vazifa → agent javobi {content, structured, source_refs}."""
        ...
    async def add_event(self, task_id: UUID, event_type: str, payload: dict[str, Any]) -> int: ...
    async def events_after(self, task_id: UUID, after_id: int, limit: int) -> list[TaskEvent]: ...
    async def idempotent_response(self, user_id: UUID, key: str) -> dict[str, Any] | None: ...
    async def save_idempotent_response(self, user_id: UUID, key: str,
                                       response: dict[str, Any]) -> None: ...


class Outbox(Protocol):
    async def publish(self, event_type: str, payload: dict[str, Any], *, aggregate_id: UUID,
                      aggregate_version: int) -> None: ...


class CapabilityIssuer(Protocol):
    def issue_for_task(self, *, task_id: UUID, tenant_id: UUID, user_id: UUID, role_key: str,
                       tools: tuple[str, ...], expires_at: datetime) -> str: ...


class QueryRefs(Protocol):
    async def exists(self, query_id: UUID) -> bool: ...


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    allowed: bool
    reservation_id: UUID | None
    message: str | None


class BudgetGate(Protocol):
    """Governance budjeti (TZ 19): vazifa AI’ga yuborilishidan oldin rezerv, yakunda sarf."""

    async def reserve(self, task_id: UUID) -> BudgetDecision: ...
    async def settle(self, task_id: UUID, usage: dict[str, Any]) -> None: ...
    async def release(self, task_id: UUID) -> None: ...
