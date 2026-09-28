import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..ports.store import AgentTaskRow, QueuedTask, StepView, TaskEvent, TaskView

_ROWS = (
    "SELECT t.id, t.conversation_id, t.initiator_id, t.agent_role_key, t.title, t.status,"
    " t.error_code, t.dispatched_at IS NOT NULL AS dispatched, s.status AS step_status,"
    " s.kind AS step_kind, s.phase AS step_phase, s.wait_reason,"
    # Aniqlashtirishga javob — shu suhbatda shu agentga keyingi vazifa (boshqa agentga xabar emas).
    " EXISTS (SELECT 1 FROM workspace.tasks n WHERE n.conversation_id = t.conversation_id"
    "   AND n.agent_role_key = t.agent_role_key AND n.created_at > t.created_at) AS answered,"
    " t.created_at, t.updated_at"
    " FROM workspace.tasks t JOIN LATERAL (SELECT * FROM workspace.task_steps x"
    "   WHERE x.task_id = t.id ORDER BY x.created_at DESC LIMIT 1) s ON true"
)
_ACTIVE = "t.status NOT IN ('succeeded', 'partial', 'failed', 'cancelled')"


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
                          step_id: UUID, *, title: str, dispatch: dict[str, Any]) -> None:
        params = {"t": self._t, "id": task_id, "conv": conversation_id, "u": user_id,
                  "role": role, "step": step_id, "title": title[:200], "d": _j(dispatch)}
        # clock_timestamp: bir tranzaksiyadagi vazifalar ham navbatda aniq tartiblanadi.
        await self._c.execute(text(
            "INSERT INTO workspace.tasks (tenant_id, id, conversation_id, initiator_id,"
            " agent_role_key, status, title, dispatch, created_at, updated_at)"
            " VALUES (:t, :id, :conv, :u, :role, 'queued', :title, CAST(:d AS jsonb),"
            " clock_timestamp(), clock_timestamp())"), params)
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
                       progress_seq: int | None, agent_run_id: UUID | None,
                       kind: str | None = None) -> None:
        await self._c.execute(text(
            "UPDATE workspace.task_steps SET status = :s, phase = coalesce(:p, phase),"
            " progress_seq = coalesce(:seq, progress_seq), kind = coalesce(:k, kind),"
            " agent_run_id = coalesce(:run, agent_run_id), updated_at = now() WHERE id = :id"),
            {"s": status, "p": phase, "seq": progress_seq, "run": agent_run_id, "k": kind,
             "id": step_id})

    async def lock_agent(self, role: str) -> None:
        await self._c.execute(text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"agent-queue:{self._t}:{role}"})

    async def count_active(self, role: str) -> int:
        r = await self._c.execute(text(
            # Muddatidan (10 daq) ancha oshgan “osilib qolgan” vazifa slotni abadiy band qilmaydi.
            "SELECT count(*) FROM workspace.tasks t WHERE t.agent_role_key = :r"
            " AND t.dispatched_at > now() - interval '15 minutes'"
            " AND t.status NOT IN ('succeeded', 'partial', 'failed', 'cancelled')"), {"r": role})
        return int(r.scalar_one())

    async def waiting(self, role: str) -> list[QueuedTask]:
        rows = (await self._c.execute(text(
            "SELECT t.id, (SELECT s.id FROM workspace.task_steps s WHERE s.task_id = t.id"
            " ORDER BY s.created_at LIMIT 1) AS step_id, t.initiator_id, t.dispatch"
            " FROM workspace.tasks t WHERE t.agent_role_key = :r AND t.dispatched_at IS NULL"
            " AND t.status = 'queued' ORDER BY t.created_at, t.id"), {"r": role})).all()
        return [QueuedTask(r.id, r.step_id, r.initiator_id, dict(r.dispatch)) for r in rows]

    async def mark_dispatched(self, task_id: UUID) -> None:
        await self._c.execute(text(
            "UPDATE workspace.tasks SET dispatched_at = now(), dispatch = NULL, updated_at = now()"
            " WHERE id = :id"), {"id": task_id})

    async def is_dispatched(self, task_id: UUID) -> bool:
        r = await self._c.execute(text(
            "SELECT dispatched_at IS NOT NULL FROM workspace.tasks WHERE id = :id"),
            {"id": task_id})
        return bool(r.scalar_one_or_none())

    async def queue_position(self, task_id: UUID) -> int | None:
        r = (await self._c.execute(text(
            "SELECT (SELECT count(*) FROM workspace.tasks o WHERE o.agent_role_key ="
            " t.agent_role_key AND o.dispatched_at IS NULL AND o.status = 'queued'"
            " AND (o.created_at, o.id) <= (t.created_at, t.id)) AS pos"
            " FROM workspace.tasks t WHERE t.id = :id AND t.dispatched_at IS NULL"
            " AND t.status = 'queued'"), {"id": task_id})).first()
        return None if r is None else int(r.pos)

    async def agent_tasks(self, since_seconds: int) -> list[AgentTaskRow]:
        """Faol vazifalar va yaqinda yakunlanganlar (yakuniy holat va aniqlashtirish uchun)."""
        rows = (await self._c.execute(text(
            _ROWS + " WHERE " + _ACTIVE + " OR t.updated_at > now() - make_interval(secs => :s)"
            " ORDER BY t.created_at"), {"s": since_seconds})).all()
        return [AgentTaskRow(*r) for r in rows]

    async def list_tasks(self, user_id: UUID, limit: int) -> list[AgentTaskRow]:
        rows = (await self._c.execute(text(
            _ROWS + " WHERE t.initiator_id = :u ORDER BY t.created_at DESC LIMIT :n"),
            {"u": user_id, "n": limit})).all()
        return [AgentTaskRow(*r) for r in rows]

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

    async def answers(self, task_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
        if not task_ids:
            return {}
        rows = (await self._c.execute(text(
            "SELECT DISTINCT ON (task_id) task_id, content, structured, source_refs"
            " FROM workspace.messages WHERE author_kind = 'agent' AND task_id = ANY(:ids)"
            " ORDER BY task_id, created_at DESC"), {"ids": task_ids})).all()
        return {r.task_id: {"content": r.content, "structured": r.structured,
                            "source_refs": r.source_refs} for r in rows}

    async def stuck_tasks(self, older_than_seconds: int) -> list[TaskView]:
        rows = (await self._c.execute(text(
            "SELECT id, conversation_id, initiator_id, agent_role_key, status, cancel_requested,"
            " error_code, limitations, created_at, updated_at FROM workspace.tasks"
            " WHERE dispatched_at < now() - make_interval(secs => :s)"
            " AND status NOT IN ('succeeded', 'partial', 'failed', 'cancelled')"
            " ORDER BY dispatched_at LIMIT 200 FOR UPDATE SKIP LOCKED"),
            {"s": older_than_seconds})).all()
        return [TaskView(*r) for r in rows]

    async def purge_conversations(self, *, days: int) -> int:
        """Eski suhbat va unga bog‘liq hamma narsa; faol vazifasi bor suhbat o‘chirilmaydi."""
        params = {"d": days}
        old = ("SELECT c.id FROM workspace.conversations c WHERE c.updated_at < now()"
               " - make_interval(days => :d) AND NOT EXISTS (SELECT 1 FROM workspace.tasks t"
               " WHERE t.conversation_id = c.id AND t.status NOT IN"
               " ('succeeded', 'partial', 'failed', 'cancelled'))")
        tasks = f"SELECT t.id FROM workspace.tasks t WHERE t.conversation_id IN ({old})"  # noqa: S608
        for table in ("task_events", "tool_calls", "task_steps"):
            await self._c.execute(text(
                f"DELETE FROM workspace.{table} WHERE task_id IN ({tasks})"), params)  # noqa: S608
        await self._c.execute(text(
            f"DELETE FROM workspace.tasks WHERE conversation_id IN ({old})"), params)  # noqa: S608
        await self._c.execute(text(
            f"DELETE FROM workspace.messages WHERE conversation_id IN ({old})"),  # noqa: S608
            params)
        r = await self._c.execute(text(
            f"DELETE FROM workspace.conversations WHERE id IN ({old})"), params)  # noqa: S608
        return int(r.rowcount or 0)

    async def purge_idempotency_keys(self, *, days: int) -> int:
        r = await self._c.execute(text(
            "DELETE FROM workspace.idempotency_keys WHERE created_at < now()"
            " - make_interval(days => :d)"), {"d": days})
        return int(r.rowcount or 0)
