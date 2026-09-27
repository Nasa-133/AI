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
                          role: str, step_id: UUID) -> None: ...
    async def get_task(self, task_id: UUID) -> TaskView | None: ...
    async def get_step(self, step_id: UUID) -> StepView | None: ...
    async def list_steps(self, task_id: UUID) -> list[StepView]: ...
    async def set_task(self, task_id: UUID, *, status: str | None = None,
                       cancel_requested: bool | None = None, error_code: str | None = None,
                       limitations: list[str] | None = None) -> None: ...
    async def set_step(self, step_id: UUID, *, status: str, phase: str | None,
                       progress_seq: int | None, agent_run_id: UUID | None) -> None: ...
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
