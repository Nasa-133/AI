"""AI Runtime eventlari → task holati, javob xabari va SSE eventlari (TZ 13.9 qadam 5–6).

Modelning “tayyor” degan matni muvaffaqiyat mezoni emas: manba havolalari Business’da
tekshiriladi, tasdiqlanmagani olib tashlanadi va cheklov sifatida ko‘rsatiladi.
"""

from typing import Any
from uuid import UUID

from ..domain.office import CLARIFICATION, PHASE_KIND
from ..domain.tasks import TaskStatus
from ..ports.store import QueryRefs, WorkspaceStore
from .dispatch import Dispatcher

_STATUS = {"succeeded": TaskStatus.SUCCEEDED, "partial": TaskStatus.PARTIAL,
           "failed": TaskStatus.FAILED, "cancelled": TaskStatus.CANCELLED}
_STEP_STATUS = {"succeeded": "succeeded", "partial": "succeeded", "failed": "failed",
                "cancelled": "cancelled"}


class AgentEventHandler:
    def __init__(self, store: WorkspaceStore, query_refs: QueryRefs,
                 dispatcher: Dispatcher) -> None:
        self._s = store
        self._refs = query_refs
        self._dispatcher = dispatcher

    async def progressed(self, p: dict[str, Any]) -> None:
        task_id, step_id = UUID(p["task_id"]), UUID(p["task_step_id"])
        task, step = await self._s.get_task(task_id), await self._s.get_step(step_id)
        if task is None or step is None or TaskStatus(task.status).is_terminal:
            return
        if p["sequence"] <= step.progress_seq:
            return  # eskirgan yoki takroriy event (tartib kafolatlanmaydi)
        await self._s.set_step(step_id, status="running", phase=p["phase"],
                               progress_seq=p["sequence"], agent_run_id=UUID(p["agent_run_id"]),
                               kind=PHASE_KIND.get(p["phase"]))
        if task.status == TaskStatus.QUEUED:
            await self._s.set_task(task_id, status=TaskStatus.RUNNING)
        await self._s.add_event(task_id, "task.progress", {
            "status": "running", "phase": p["phase"], "message": p["message"],
            "tool_calls_used": p["tool_calls_used"]})

    async def completed(self, p: dict[str, Any]) -> None:
        task_id, step_id = UUID(p["task_id"]), UUID(p["task_step_id"])
        task = await self._s.get_task(task_id)
        if task is None or TaskStatus(task.status).is_terminal:
            return
        limitations = list(p["limitations"])
        refs = []
        for ref in p["source_refs"]:
            if ref["kind"] == "query_result" and not await self._refs.exists(UUID(ref["id"])):
                limitations.append("Tasdiqlanmagan manba havolasi olib tashlandi.")
                continue
            refs.append(ref)
        status = _STATUS[p["status"]]
        candidate = p["result_candidate"]
        answer = (candidate or {}).get("answer_markdown")
        if answer:
            await self._s.add_message({
                "conversation_id": task.conversation_id, "author_kind": "agent",
                "agent_role_key": task.agent_role_key, "content": answer, "task_id": task_id,
                "structured": (candidate or {}).get("structured"), "source_refs": refs})
        elif status is TaskStatus.SUCCEEDED:
            # Javobsiz “muvaffaqiyat” qabul qilinmaydi.
            status = TaskStatus.FAILED
            limitations.append("Agent javob matnini qaytarmadi.")
        await self._s.set_step(step_id, status=_STEP_STATUS[p["status"]], phase=None,
                               progress_seq=None, agent_run_id=UUID(p["agent_run_id"]))
        await self._s.set_task(task_id, status=status, error_code=p["error_code"],
                               limitations=limitations)
        await self._s.add_event(task_id, "task.completed", {
            "status": status.value, "error_code": p["error_code"], "limitations": limitations,
            "has_answer": bool(answer), "structured": (candidate or {}).get("structured"),
            "needs_input": p["error_code"] == CLARIFICATION})
        # Slot bo‘shadi — shu agent navbatidagi keyingi vazifa yuboriladi (TZ 4).
        await self._dispatcher.pump(task.agent_role_key)
