"""Agent navbati (TZ 4, T01): har agent uchun parallel ishlar limiti.

Limit to‘lsa vazifa shu agent navbatida qoladi — boshqa mutaxassislikka o‘tkazilmaydi.
Slot bo‘shaganda (vazifa yakunlanganda) navbatdagi birinchi vazifa yuboriladi. Bir agentning
navbati tranzaksiya darajasidagi advisory lock bilan ketma-ketlashtiriladi (poyga yo‘q).
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from ..ports.store import CapabilityIssuer, Outbox, QueuedTask, WorkspaceStore

TASK_DEADLINE = timedelta(minutes=10)


class Dispatcher:
    def __init__(self, store: WorkspaceStore, outbox: Outbox, capabilities: CapabilityIssuer, *,
                 tenant_id: UUID, limit: int, policy_version: int,
                 clock: Callable[[], datetime]) -> None:
        self._s = store
        self._outbox = outbox
        self._caps = capabilities
        self._tenant = tenant_id
        self._limit = max(1, limit)
        self._policy_version = policy_version
        self._clock = clock

    @property
    def limit(self) -> int:
        return self._limit

    async def pump(self, role: str, *, announce: bool = True) -> dict[UUID, int]:
        """Bo‘sh slotlarga navbatdagilarni yuboradi; qolganlarning navbatdagi o‘rnini qaytaradi.

        `announce` — o‘rni o‘zgargan vazifalarga `task.queued` SSE eventi yoziladi."""
        await self._s.lock_agent(role)
        free = self._limit - await self._s.count_active(role)
        waiting = await self._s.waiting(role)
        sent = waiting[:max(free, 0)]
        for q in sent:
            await self._send(q, role)
        positions = {q.task_id: i for i, q in enumerate(waiting[len(sent):], start=1)}
        if announce:
            for task_id, position in positions.items():
                await self._s.add_event(task_id, "task.queued",
                                        {"status": "queued", "queue_position": position})
        return positions

    async def _send(self, q: QueuedTask, role: str) -> None:
        now = self._clock()
        deadline = now + TASK_DEADLINE  # navbatda kutilgan vaqt limitga kirmaydi
        d = q.dispatch
        token = self._caps.issue_for_task(
            task_id=q.task_id, tenant_id=self._tenant, user_id=q.initiator_id, role_key=role,
            tools=tuple(d["tools"]), expires_at=deadline)
        await self._outbox.publish("RunAgent.v1", {
            "task_id": str(q.task_id), "task_step_id": str(q.step_id), "agent_role_key": role,
            "sanitized_instruction": d["instruction"], "context_refs": d["context_refs"],
            "deadline": deadline.isoformat(),
            # Budjet rezervi Bosqich 5 da; hozircha faqat identifikator (limit qo‘llanmaydi).
            "budget_reservation_id": str(uuid4()), "policy_version": self._policy_version,
            "locale": d.get("locale", "uz-Latn"), "capability_token": token,
        }, aggregate_id=q.task_id, aggregate_version=1)
        await self._s.mark_dispatched(q.task_id)
