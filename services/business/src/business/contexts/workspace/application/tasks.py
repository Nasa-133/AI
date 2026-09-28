"""Chat xabari → task → RunAgent (TZ 13.9 qadam 1–2), bekor qilish, holatni o‘qish."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from business.kernel.errors import BusinessError

from ..domain.tasks import AGENTS, TaskNotCancellable, TaskStatus, route, sanitize
from ..ports.store import Outbox, TaskView, WorkspaceStore
from .dispatch import Dispatcher

TITLE_CHARS = 120


class NotFound(BusinessError):
    code = "NOT_FOUND"


@dataclass(frozen=True, slots=True)
class Actor:
    tenant_id: UUID
    user_id: UUID
    role: str  # foydalanuvchi roli (owner/admin/analyst/viewer)
    allowed_tools: tuple[str, ...]  # Governance: agent roli ∩ foydalanuvchi roli


class TaskService:
    def __init__(self, store: WorkspaceStore, outbox: Outbox, dispatcher: Dispatcher,
                 tools_for: Any) -> None:
        self._s = store
        self._outbox = outbox
        self._dispatcher = dispatcher
        self._tools_for = tools_for

    async def start_conversation(self, actor: Actor, title: str) -> UUID:
        conversation_id = uuid4()
        await self._s.create_conversation(conversation_id, title.strip() or "Yangi suhbat",
                                          actor.user_id)
        return conversation_id

    async def post_message(self, actor: Actor, conversation_id: UUID, content: str, *,
                           agent: str | None, idempotency_key: str | None,
                           now: datetime, context_documents: list[dict[str, Any]] | None = None,
                           ) -> dict[str, Any]:
        """`context_documents` — foydalanuvchi ko‘ra oladigan hujjatlar (ACL chaqiruvchida
        tekshirilgan): [{id, version_id, title}].

        Vazifa avval agent navbatiga yoziladi; limit bo‘sh bo‘lsa darhol yuboriladi (T01)."""
        if idempotency_key and (done := await self._s.idempotent_response(actor.user_id,
                                                                          idempotency_key)):
            return done  # takroriy yuborish: yangi task yo‘q (T04)
        if not await self._s.conversation_exists(conversation_id):
            raise NotFound("Suhbat topilmadi.")
        text = sanitize(content)
        documents = context_documents or []
        role = route(text, agent, has_documents=bool(documents),
                     awaiting_role=await self._s.awaiting_answer_role(conversation_id))
        tools = sorted(self._tools_for(role, actor.role))
        message_id, task_id, step_id = uuid4(), uuid4(), uuid4()
        await self._s.add_message({"id": message_id, "conversation_id": conversation_id,
                                   "author_kind": "user", "author_id": actor.user_id,
                                   "content": text, "task_id": task_id,
                                   "structured": {"context_documents": documents}
                                   if documents else None})
        title = " ".join(text.split())
        await self._s.create_task(
            task_id, conversation_id, actor.user_id, role, step_id,
            title=title if len(title) <= TITLE_CHARS else title[:TITLE_CHARS - 1] + "…",
            dispatch={"instruction": text, "tools": tools, "locale": "uz-Latn",
                      "context_refs": [{"kind": "document_version", "id": d["id"],
                                        "version_id": d["version_id"], "locator": None}
                                       for d in documents]})
        positions = await self._dispatcher.pump(role, announce=False)
        position = positions.get(task_id)
        name, agent_title = AGENTS[role]
        await self._s.add_event(task_id, "task.created", {
            "status": "queued", "agent_role_key": role, "agent_name": name,
            "agent_title": agent_title, "queue_position": position})
        response = {"task_id": str(task_id), "message_id": str(message_id),
                    "agent_role_key": role, "agent_name": name, "queue_position": position}
        if idempotency_key:
            await self._s.save_idempotent_response(actor.user_id, idempotency_key, response)
        return response

    async def cancel(self, actor: Actor, task_id: UUID) -> None:
        task = await self._require(task_id)
        if TaskStatus(task.status).is_terminal:
            raise TaskNotCancellable("Vazifa allaqachon tugagan.")
        if task.cancel_requested:
            return
        steps = await self._s.list_steps(task_id)
        await self._s.lock_agent(task.agent_role_key)  # navbat bilan poyga bo‘lmasin
        if not await self._s.is_dispatched(task_id):
            # Navbatdagi vazifa hali AI’ga yuborilmagan — darhol bekor qilinadi, sarf yo‘q (T05).
            await self._s.set_task(task_id, status=TaskStatus.CANCELLED, cancel_requested=True)
            for step in steps:
                await self._s.set_step(step.id, status="cancelled", phase=None,
                                       progress_seq=None, agent_run_id=None)
            await self._s.add_event(task_id, "task.completed", {
                "status": "cancelled", "error_code": None, "limitations": [],
                "has_answer": False, "structured": None})
            await self._dispatcher.pump(task.agent_role_key)
            return
        await self._s.set_task(task_id, cancel_requested=True)
        await self._outbox.publish("CancelAgentRun.v1", {
            "task_id": str(task_id), "task_step_id": str(steps[0].id),
            "requested_by": str(actor.user_id), "reason": "Foydalanuvchi bekor qildi"},
            aggregate_id=task_id, aggregate_version=2)
        await self._s.add_event(task_id, "task.cancel_requested", {"status": task.status})

    async def detail(self, task_id: UUID) -> dict[str, Any]:
        task = await self._require(task_id)
        steps = await self._s.list_steps(task_id)
        return {"id": str(task.id), "conversation_id": str(task.conversation_id),
                "status": task.status, "agent_role_key": task.agent_role_key,
                "cancel_requested": task.cancel_requested, "error_code": task.error_code,
                "queue_position": await self._s.queue_position(task_id),
                "limitations": task.limitations,
                "steps": [{"id": str(s.id), "status": s.status, "phase": s.phase,
                           "agent_role_key": s.agent_role_key} for s in steps],
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat()}

    async def _require(self, task_id: UUID) -> TaskView:
        task = await self._s.get_task(task_id)
        if task is None:
            raise NotFound("Vazifa topilmadi.")
        return task
