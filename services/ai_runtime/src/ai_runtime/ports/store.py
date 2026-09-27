from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol
from uuid import UUID

from ..domain.run import AgentRun


@dataclass(frozen=True, slots=True)
class PendingEvent:
    """Outbox’ga yoziladigan event (envelope’ni adapter quradi)."""

    event_type: str
    payload: dict[str, Any]
    aggregate_version: int


class LeaseLost(Exception):
    """Lease boshqa worker’ga o‘tgan: bu worker run’ni tashlab ketadi."""


class RunCommands(Protocol):
    """Consumer tranzaksiyasi ichida (envelope tenant konteksti bog‘langan)."""

    async def create_if_absent(self, run: AgentRun) -> bool: ...
    async def request_cancel(self, task_step_id: UUID) -> bool: ...


class RunStore(Protocol):
    async def claim(self, owner: str, lease: timedelta) -> AgentRun | None:
        """Navbatdan bitta bo‘sh yoki lease’i tugagan run’ni oladi."""
        ...

    async def refresh_cancel(self, run: AgentRun) -> bool: ...

    async def commit_step(self, run: AgentRun, owner: str, lease: timedelta,
                          events: list[PendingEvent]) -> None:
        """Run holati, checkpoint va eventlarni bitta tranzaksiyada saqlaydi.

        Lease hali shu worker’da bo‘lmasa `LeaseLost`. Run yakuniy holatda bo‘lsa navbatdan
        chiqariladi.
        """
        ...
