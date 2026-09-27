"""AgentRun holat mashinasi (TZ 11, 13.9). Toza: I/O va framework yo‘q."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from .errors import InvalidTransition, ToolBudgetExceeded, ToolNotAllowed
from .roles import KNOWN_TOOLS, allowed_tools


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_final(self) -> bool:
        return self in _FINAL


_FINAL = {RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.CANCELLED}
_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED},
    RunStatus.RUNNING: {RunStatus.RUNNING} | _FINAL,
}


@dataclass(slots=True)
class Checkpoint:
    """Model bilan suhbat holati. `items` Responses API input formatida saqlanadi."""

    items: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    def pending_tool_calls(self) -> list[dict[str, Any]]:
        """Chiqishi hali yozilmagan function_call elementlari (tartib saqlanadi)."""
        done = {i["call_id"] for i in self.items if i.get("type") == "function_call_output"}
        return [i for i in self.items
                if i.get("type") == "function_call" and i["call_id"] not in done]

    def tool_outputs(self) -> dict[str, str]:
        return {i["call_id"]: i["output"] for i in self.items
                if i.get("type") == "function_call_output"}

    def to_json(self) -> dict[str, Any]:
        return {"items": self.items, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens}

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> "Checkpoint":
        data = data or {}
        return cls(items=list(data.get("items", [])),
                   input_tokens=int(data.get("input_tokens", 0)),
                   output_tokens=int(data.get("output_tokens", 0)))


@dataclass(slots=True)
class AgentRun:
    id: UUID
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
    max_tool_calls: int
    status: RunStatus = RunStatus.QUEUED
    tool_calls_used: int = 0
    cancel_requested: bool = False
    sequence: int = 0
    checkpoint: Checkpoint = field(default_factory=Checkpoint)

    def _move(self, target: RunStatus) -> None:
        if target not in _TRANSITIONS.get(self.status, set()):
            raise InvalidTransition(f"{self.status} → {target} mumkin emas")
        self.status = target

    def start(self) -> None:
        """Birinchi claim yoki lease tugagach boshqa worker davom ettirishi."""
        if self.status is RunStatus.RUNNING:
            return
        self._move(RunStatus.RUNNING)

    def is_past_deadline(self, now: datetime) -> bool:
        return now >= self.deadline

    def request_cancel(self) -> bool:
        """Yakunlangan run’ni bekor qilib bo‘lmaydi — tugagan ish ortga qaytmaydi."""
        if self.status.is_final:
            return False
        self.cancel_requested = True
        return True

    def ensure_tool_allowed(self, name: str) -> None:
        if name not in KNOWN_TOOLS or name not in allowed_tools(self.role_key):
            raise ToolNotAllowed(f"`{name}` vositasi {self.role_key} uchun ruxsat etilmagan")

    def has_tool_budget(self) -> bool:
        return self.tool_calls_used < self.max_tool_calls

    def record_tool_call(self) -> None:
        if not self.has_tool_budget():
            raise ToolBudgetExceeded(f"Tool chaqiruvlari limiti ({self.max_tool_calls}) tugadi")
        self.tool_calls_used += 1

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence

    def finish(self, status: RunStatus) -> None:
        if not status.is_final:
            raise InvalidTransition(f"{status} yakuniy holat emas")
        self._move(status)
