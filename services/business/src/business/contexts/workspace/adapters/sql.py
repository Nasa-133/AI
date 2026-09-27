import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..ports.store import StepView, TaskEvent, TaskView


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class SqlWorkspaceStore:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._c = conn
        self._t = tenant_id

    async def create_conversation(self, conversation_id: UUID, title: str, user_id: UUID) -> None:
        await self._c.execute(text(
            "INSERT INTO workspace.conversations (tenant_id, id, title, created_by, created_at,"
            " updated_at) VALUES (:t, :id, :title, :by, now(), now())"),
            {"t": self._t, "id": conversation_id, "title": title[:200], "by": user_id})

    async def conversation_exists(self, conversation_id: UUID) -> bool:
        r = await self._c.execute(text("SELECT 1 FROM workspace.conversations WHERE id = :id"),
                                  {"id": conversation_id})
        return r.first() is not None

    async def list_conversations(self, user_id: UUID, limit: int) -> list[dict[str, Any]]:
        rows = (await self._c.execute(text(
            "SELECT id, title, created_at, updated_at FROM workspace.conversations"
            " WHERE created_by = :u ORDER BY updated_at DESC LIMIT :n"),
            {"u": user_id, "n": limit})).mappings().all()
        return [dict(r) for r in rows]

    async def list_messages(self, conversation_id: UUID, limit: int) -> list[dict[str, Any]]:
        rows = (await self._c.execute(text(
            "SELECT id, author_kind, author_id, agent_role_key, content, task_id, structured,"
            " source_refs, created_at FROM workspace.messages WHERE conversation_id = :c"
            " ORDER BY created_at, id LIMIT :n"), {"c": conversation_id, "n": limit})).mappings()
        return [dict(r) for r in rows.all()]

    async def add_message(self, m: dict[str, Any]) -> None:
        await self._c.execute(text(
            "INSERT INTO workspace.messages (tenant_id, id, conversation_id, author_kind,"
            " author_id, agent_role_key, content, task_id, structured, source_refs, created_at)"
            " VALUES (:t, :id, :conv, :kind, :author, :role, :content, :task,"
            " CAST(:structured AS jsonb), CAST(:refs AS jsonb), clock_timestamp())"),
            {"t": self._t, "id": m.get("id") or uuid4(), "conv": m["conversation_id"],
             "kind": m["author_kind"], "author": m.get("author_id"),
             "role": m.get("agent_role_key"),
             "content": m["content"], "task": m.get("task_id"),
             "structured": _j(m.get("structured")), "refs": _j(m.get("source_refs") or [])})
        await self._c.execute(text(
            "UPDATE workspace.conversations SET updated_at = now() WHERE id = :id"),
            {"id": m["conversation_id"]})

    async def create_task(self, task_id: UUID, conversation_id: UUID, user_id: UUID, role: str,
                          step_id: UUID) -> None:
        params = {"t": self._t, "id": task_id, "conv": conversation_id, "u": user_id,
                  "role": role, "step": step_id}
        await self._c.execute(text(
            "INSERT INTO workspace.tasks (tenant_id, id, conversation_id, initiator_id,"
            " agent_role_key, status, created_at, updated_at)"
            " VALUES (:t, :id, :conv, :u, :role, 'queued', now(), now())"), params)
        await self._c.execute(text(
            "INSERT INTO workspace.task_steps (tenant_id, id, task_id, agent_role_key, kind,"
            " status, created_at, updated_at) VALUES (:t, :step, :id, :role, 'analyze',"
            " 'pending', now(), now())"), params)

    async def get_task(self, task_id: UUID) -> TaskView | None:
        r = (await self._c.execute(text(
            "SELECT id, conversation_id, initiator_id, agent_role_key, status, cancel_requested,"
            " error_code, limitations, created_at, updated_at FROM workspace.tasks WHERE id = :id"),
            {"id": task_id})).first()
        return None if r is None else TaskView(*r)

    async def get_step(self, step_id: UUID) -> StepView | None:
        r = (await self._c.execute(text(
            "SELECT id, task_id, agent_role_key, status, phase, progress_seq"
            " FROM workspace.task_steps WHERE id = :id"), {"id": step_id})).first()
        return None if r is None else StepView(*r)

    async def list_steps(self, task_id: UUID) -> list[StepView]:
        rows = (await self._c.execute(text(
            "SELECT id, task_id, agent_role_key, status, phase, progress_seq"
            " FROM workspace.task_steps WHERE task_id = :id ORDER BY created_at"),
            {"id": task_id})).all()
        return [StepView(*r) for r in rows]

    async def set_task(self, task_id: UUID, *, status: str | None = None,
                       cancel_requested: bool | None = None, error_code: str | None = None,
                       limitations: list[str] | None = None) -> None:
        await self._c.execute(text(
            "UPDATE workspace.tasks SET status = coalesce(:s, status),"
            " cancel_requested = coalesce(:c, cancel_requested),"
            " error_code = coalesce(:e, error_code),"
            " limitations = coalesce(CAST(:l AS jsonb), limitations), updated_at = now()"
            " WHERE id = :id"),
            {"s": status, "c": cancel_requested, "e": error_code,
             "l": None if limitations is None else _j(limitations), "id": task_id})

    async def set_step(self, step_id: UUID, *, status: str, phase: str | None,
                       progress_seq: int | None, agent_run_id: UUID | None) -> None:
        await self._c.execute(text(
            "UPDATE workspace.task_steps SET status = :s, phase = coalesce(:p, phase),"
            " progress_seq = coalesce(:seq, progress_seq),"
            " agent_run_id = coalesce(:run, agent_run_id), updated_at = now() WHERE id = :id"),
            {"s": status, "p": phase, "seq": progress_seq, "run": agent_run_id, "id": step_id})

    async def add_event(self, task_id: UUID, event_type: str, payload: dict[str, Any]) -> int:
        r = await self._c.execute(text(
            "INSERT INTO workspace.task_events (tenant_id, task_id, event_type, payload,"
            " created_at) VALUES (:t, :task, :type, CAST(:p AS jsonb), now()) RETURNING id"),
            {"t": self._t, "task": task_id, "type": event_type, "p": _j(payload)})
        return int(r.scalar_one())

    async def events_after(self, task_id: UUID, after_id: int, limit: int) -> list[TaskEvent]:
        rows = (await self._c.execute(text(
            "SELECT id, event_type, payload, created_at FROM workspace.task_events"
            " WHERE task_id = :task AND id > :after ORDER BY id LIMIT :n"),
            {"task": task_id, "after": after_id, "n": limit})).all()
        return [TaskEvent(*r) for r in rows]

    async def idempotent_response(self, user_id: UUID, key: str) -> dict[str, Any] | None:
        r = (await self._c.execute(text(
            "SELECT response FROM workspace.idempotency_keys WHERE user_id = :u AND key = :k"),
            {"u": user_id, "k": key})).first()
        return None if r is None else dict(r.response)

    async def save_idempotent_response(self, user_id: UUID, key: str,
                                       response: dict[str, Any]) -> None:
        await self._c.execute(text(
            "INSERT INTO workspace.idempotency_keys (tenant_id, user_id, key, response, created_at)"
            " VALUES (:t, :u, :k, CAST(:r AS jsonb), now())"),
            {"t": self._t, "u": user_id, "k": key, "r": _j(response)})
