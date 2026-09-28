"""Agent navbati (TZ 4, T01): har agent uchun parallel ishlar limiti.

Limit to‘lsa vazifa shu agent navbatida qoladi — boshqa mutaxassislikka o‘tkazilmaydi.
Slot bo‘shaganda (vazifa yakunlanganda) navbatdagi birinchi vazifa yuboriladi. Bir agentning
navbati tranzaksiya darajasidagi advisory lock bilan ketma-ketlashtiriladi (poyga yo‘q).
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from ..domain.tasks import TaskStatus
from ..ports.store import (
    BudgetGate,
    CapabilityIssuer,
    Outbox,
    PrivacyGate,
    QueuedTask,
    WorkspaceStore,
)

TASK_DEADLINE = timedelta(minutes=10)
CONVERSATION_TURNS = 8  # RunAgent.v1 conversation.maxItems
CONVERSATION_CHARS = 2000


class Dispatcher:
    def __init__(self, store: WorkspaceStore, outbox: Outbox, capabilities: CapabilityIssuer, *,
                 tenant_id: UUID, limit: int, policy_version: int,
                 clock: Callable[[], datetime], budget: BudgetGate,
                 privacy: PrivacyGate) -> None:
        self._budget = budget
        self._privacy = privacy
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
        sent: list[QueuedTask] = []
        rest = list(waiting)
        while rest and len(sent) < free:
            q = rest.pop(0)
            if await self._send(q, role):
                sent.append(q)
        waiting = sent + rest
        positions = {q.task_id: i for i, q in enumerate(waiting[len(sent):], start=1)}
        if announce:
            for q in sent:  # navbatdan chiqdi — AI’ga yuborildi
                await self._s.add_event(q.task_id, "task.queued",
                                        {"status": "queued", "queue_position": None})
            for task_id, position in positions.items():
                await self._s.add_event(task_id, "task.queued",
                                        {"status": "queued", "queue_position": position})
        return positions

    async def _send(self, q: QueuedTask, role: str) -> bool:
        """Budjet rezervi olinmasa vazifa aniq sabab bilan yakunlanadi (False)."""
        decision = await self._budget.reserve(q.task_id)
        if not decision.allowed:
            await self._reject(q, decision.message or "AI budjeti limiti tugagan.")
            return False
        now = self._clock()
        deadline = now + TASK_DEADLINE  # navbatda kutilgan vaqt limitga kirmaydi
        d = q.dispatch
        token = self._caps.issue_for_task(
            task_id=q.task_id, tenant_id=self._tenant, user_id=q.initiator_id, role_key=role,
            tools=tuple(d["tools"]), expires_at=deadline)
        await self._outbox.publish("RunAgent.v1", {
            "task_id": str(q.task_id), "task_step_id": str(q.step_id), "agent_role_key": role,
            "sanitized_instruction": await self._privacy.mask_instruction(q.task_id,
                                                                          d["instruction"]),
            "context_refs": d["context_refs"],
            "conversation": await self._conversation(q.task_id),
            "deadline": deadline.isoformat(),
            "budget_reservation_id": str(decision.reservation_id or uuid4()),
            "policy_version": self._policy_version,
            "locale": d.get("locale", "uz-Latn"), "capability_token": token,
        }, aggregate_id=q.task_id, aggregate_version=1)
        await self._s.mark_dispatched(q.task_id)
        return True

    async def _conversation(self, task_id: UUID) -> list[dict[str, Any]]:
        """Oldingi xabarlar: “barchasi”, “ha, filiallar bo‘yicha” kabi davom savollar tushunilsin.

        Matn AI’ga ketadi — shuning uchun ko‘rsatma bilan bir xil psevdonimlanadi va qisqartiriladi.
        """
        out = []
        for m in await self._s.conversation_before(task_id, CONVERSATION_TURNS):
            text = str(m["content"] or "").strip()
            if len(text) > CONVERSATION_CHARS:
                # Bosh (xulosa) va oxir (manbalar: snapshot/query ID’lari) saqlanadi — “shu hisobot
                # bo‘yicha dashboard” kabi so‘rovlar aynan o‘sha natijaga bog‘lanadi.
                tail = CONVERSATION_CHARS * 2 // 5
                text = text[:CONVERSATION_CHARS - tail - 5] + "\n[…]\n" + text[-tail:]
            out.append({"role": m["author_kind"], "agent_role_key": m["agent_role_key"],
                        "text": await self._privacy.mask_instruction(task_id, text)})
        return out

    async def _reject(self, q: QueuedTask, message: str) -> None:
        task = await self._s.get_task(q.task_id)
        await self._s.mark_dispatched(q.task_id)  # navbatdan chiqadi (AI’ga yuborilmaydi)
        await self._s.set_task(q.task_id, status=TaskStatus.FAILED, error_code="BUDGET_EXCEEDED",
                               limitations=[message])
        await self._s.set_step(q.step_id, status="failed", phase=None, progress_seq=None,
                               agent_run_id=None)
        if task is not None:
            await self._s.add_message({
                "conversation_id": task.conversation_id, "author_kind": "agent",
                "agent_role_key": task.agent_role_key, "content": message, "task_id": q.task_id,
                "structured": {"error_code": "BUDGET_EXCEEDED"}, "source_refs": []})
        await self._s.add_event(q.task_id, "task.completed", {
            "status": "failed", "error_code": "BUDGET_EXCEEDED", "limitations": [message],
            "has_answer": True, "structured": None})
