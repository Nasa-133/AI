import copy
from datetime import timedelta
from uuid import UUID

from ai_runtime.domain.run import AgentRun
from ai_runtime.ports.store import LeaseLost, PendingEvent


class MemoryStore:
    def __init__(self) -> None:
        self.runs: dict[UUID, AgentRun] = {}
        self.leases: dict[UUID, str] = {}
        self.queue: list[UUID] = []
        self.events: list[PendingEvent] = []

    def add(self, run: AgentRun) -> None:
        self.runs[run.id] = copy.deepcopy(run)
        self.queue.append(run.id)

    async def claim(self, owner: str, lease: timedelta) -> AgentRun | None:
        for run_id in self.queue:
            if run_id not in self.leases:
                self.leases[run_id] = owner
                return copy.deepcopy(self.runs[run_id])
        return None

    def expire(self, run_id: UUID) -> None:
        self.leases.pop(run_id, None)

    async def refresh_cancel(self, run: AgentRun) -> bool:
        run.cancel_requested = self.runs[run.id].cancel_requested
        return run.cancel_requested

    async def commit_step(self, run: AgentRun, owner: str, lease: timedelta,
                          events: list[PendingEvent]) -> None:
        if self.leases.get(run.id) != owner:
            raise LeaseLost(str(run.id))
        run.cancel_requested = self.runs[run.id].cancel_requested
        self.runs[run.id] = copy.deepcopy(run)
        self.events.extend(events)
        if run.status.is_final:
            self.queue.remove(run.id)
            del self.leases[run.id]
