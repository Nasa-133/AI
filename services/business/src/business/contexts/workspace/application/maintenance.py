"""Workspace fon ishlari (worker davriy chaqiradi, tenant RLS kontekstida).

- Osilib qolgan vazifa: AI’ga yuborilgan, muddati (10 daq) + zaxira o‘tgan, yakunlanmagan —
  aniq sabab bilan `failed`, budjet rezervi bo‘shatiladi, navbatdagi vazifa yuboriladi.
- Retention (TZ 17): suhbatlar N kundan keyin (standart 90) o‘chiriladi;
  faol vazifasi bor suhbat o‘chirilmaydi.
"""

from datetime import timedelta

from ..domain.tasks import TaskStatus
from ..ports.store import BudgetGate, WorkspaceStore
from .dispatch import TASK_DEADLINE, Dispatcher

STUCK_GRACE = timedelta(minutes=5)
TIMEOUT_MESSAGE = ("Vazifa belgilangan vaqt ichida yakunlanmadi (AI xizmati javob bermadi). "
                   "Natija taxmin qilinmadi — keyinroq qayta yuboring.")


class WorkspaceMaintenance:
    def __init__(self, store: WorkspaceStore, dispatcher: Dispatcher, budget: BudgetGate) -> None:
        self._s = store
        self._dispatcher = dispatcher
        self._budget = budget

    async def reap_stuck(self) -> int:
        stuck = await self._s.stuck_tasks(int((TASK_DEADLINE + STUCK_GRACE).total_seconds()))
        roles: set[str] = set()
        for task in stuck:
            await self._s.set_task(task.id, status=TaskStatus.FAILED, error_code="TASK_TIMEOUT",
                                   limitations=[TIMEOUT_MESSAGE])
            for step in await self._s.list_steps(task.id):
                if step.status not in ("succeeded", "failed", "cancelled", "skipped"):
                    await self._s.set_step(step.id, status="failed", phase=None,
                                           progress_seq=None, agent_run_id=None)
            await self._s.add_message({
                "conversation_id": task.conversation_id, "author_kind": "agent",
                "agent_role_key": task.agent_role_key, "content": TIMEOUT_MESSAGE,
                "task_id": task.id, "structured": {"error_code": "TASK_TIMEOUT"},
                "source_refs": []})
            await self._s.add_event(task.id, "task.completed", {
                "status": "failed", "error_code": "TASK_TIMEOUT", "limitations": [TIMEOUT_MESSAGE],
                "has_answer": True, "structured": None})
            await self._budget.release(task.id)
            roles.add(task.agent_role_key)
        for role in roles:
            await self._dispatcher.pump(role)
        return len(stuck)

    async def apply_retention(self, conversation_days: int) -> int:
        await self._s.purge_idempotency_keys(days=7)
        return await self._s.purge_conversations(days=conversation_days)
