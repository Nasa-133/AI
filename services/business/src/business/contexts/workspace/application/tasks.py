"""Chat xabari → task → RunAgent (TZ 13.9 qadam 1–2), bekor qilish, holatni o‘qish."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from business.kernel.errors import BusinessError

from ..domain.tasks import AGENTS, TaskNotCancellable, TaskStatus, route, sanitize
from ..ports.store import CapabilityIssuer, Outbox, TaskView, WorkspaceStore

TASK_DEADLINE = timedelta(minutes=10)


class NotFound(BusinessError):
    code = "NOT_FOUND"


@dataclass(frozen=True, slots=True)
class Actor:
    tenant_id: UUID
    user_id: UUID
    role: str  # foydalanuvchi roli (owner/admin/analyst/viewer)
    allowed_tools: tuple[str, ...]  # Governance: agent roli ∩ foydalanuvchi roli


class TaskService:
    def __init__(self, store: WorkspaceStore, outbox: Outbox, capabilities: CapabilityIssuer,
                 tools_for: Any, policy_version: int) -> None:
        self._s = store
        self._outbox = outbox
        self._caps = capabilities
        self._tools_for = tools_for
        self._policy_version = policy_version

    async def start_conversation(self, actor: Actor, title: str) -> UUID:
        conversation_id = uuid4()
        await self._s.create_conversation(conversation_id, title.strip() or "Yangi suhbat",
                                          actor.user_id)
        return conversation_id

    async def post_message(self, actor: Actor, conversation_id: UUID, content: str, *,
                           agent: str | None, idempotency_key: str | None,
                           now: datetime) -> dict[str, Any]:
        if idempotency_key and (done := await self._s.idempotent_response(actor.user_id,
                                                                          idempotency_key)):
            return done  # takroriy yuborish: yangi task yo‘q (T04)
        if not await self._s.conversation_exists(conversation_id):
            raise NotFound("Suhbat topilmadi.")
        text = sanitize(content)
        role = route(text, agent)
        tools = tuple(sorted(self._tools_for(role, actor.role)))
        message_id, task_id, step_id = uuid4(), uuid4(), uuid4()
        await self._s.add_message({"id": message_id, "conversation_id": conversation_id,
                                   "author_kind": "user", "author_id": actor.user_id,
                                   "content": text, "task_id": task_id})
        await self._s.create_task(task_id, conversation_id, actor.user_id, role, step_id)
        deadline = now + TASK_DEADLINE
        token = self._caps.issue_for_task(task_id=task_id, tenant_id=actor.tenant_id,
                                          user_id=actor.user_id, role_key=role, tools=tools,
                                          expires_at=deadline)
        await self._outbox.publish("RunAgent.v1", {
            "task_id": str(task_id), "task_step_id": str(step_id), "agent_role_key": role,
            "sanitized_instruction": text, "context_refs": [], "deadline": deadline.isoformat(),
            # Budjet rezervi Bosqich 5 da; hozircha faqat identifikator (limit qo‘llanmaydi).
            "budget_reservation_id": str(uuid4()), "policy_version": self._policy_version,
            "locale": "uz-Latn", "capability_token": token,
        }, aggregate_id=task_id, aggregate_version=1)
        name, title = AGENTS[role]
        await self._s.add_event(task_id, "task.created", {
            "status": "queued", "agent_role_key": role, "agent_name": name, "agent_title": title})
        response = {"task_id": str(task_id), "message_id": str(message_id),
                    "agent_role_key": role, "agent_name": name}
        if idempotency_key:
            await self._s.save_idempotent_response(actor.user_id, idempotency_key, response)
        return response

    async def cancel(self, actor: Actor, task_id: UUID) -> None:
        task = await self._require(task_id)
        if TaskStatus(task.status).is_terminal:
            raise TaskNotCancellable("Vazifa allaqachon tugagan.")
        if task.cancel_requested:
            return
        await self._s.set_task(task_id, cancel_requested=True)
        steps = await self._s.list_steps(task_id)
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
