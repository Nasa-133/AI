"""Ofis ko‘rinishi (TZ 6): har agent holati, joriy ishlar soni, navbat va joriy vazifa.

Boshqa foydalanuvchining vazifa matni ko‘rsatilmaydi — faqat “band” ekanligi (maxfiylik).
"""

from collections import defaultdict
from datetime import datetime
from typing import Any

from ..domain.office import (
    IDLE_AFTER,
    INPUT_WAIT_MAX,
    TERMINAL_TASK,
    AgentState,
    AgentTask,
    agent_state,
)
from ..domain.tasks import AGENTS
from ..ports.store import AgentTaskRow, WorkspaceStore


def _agent_task(r: AgentTaskRow) -> AgentTask:
    step_status = r.step_status if r.dispatched else "pending"
    return AgentTask(str(r.task_id), r.status, step_status, r.step_kind, r.wait_reason,
                     r.error_code, r.updated_at, r.answered, r.dispatched)


def task_view(r: AgentTaskRow, viewer_id: object, position: int | None) -> dict[str, Any]:
    mine = r.initiator_id == viewer_id
    return {"id": str(r.task_id), "mine": mine, "title": r.title if mine else None,
            "conversation_id": str(r.conversation_id) if mine else None,
            "agent_role_key": r.agent_role_key, "status": r.status, "phase": r.step_phase,
            "kind": r.step_kind, "error_code": r.error_code, "queue_position": position,
            "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat()}


def _positions(rows: list[AgentTaskRow]) -> dict[object, int]:
    queued = [r for r in rows if not r.dispatched and r.status == "queued"]
    return {r.task_id: i for i, r in enumerate(sorted(queued, key=lambda r: r.created_at), 1)}


RESULT_CHARS = 1200


def _result(row: AgentTaskRow | None, answers: dict[Any, dict[str, Any]],
            viewer_id: object) -> dict[str, Any] | None:
    if row is None:
        return None
    answer = answers.get(row.task_id) or {}
    content = str(answer.get("content") or "")
    structured = answer.get("structured") or {}
    return {**task_view(row, viewer_id, None),
            "answer": content if len(content) <= RESULT_CHARS
            else content[:RESULT_CHARS].rstrip() + "…",
            "truncated": len(content) > RESULT_CHARS,
            "dashboard_ids": list(structured.get("dashboard_ids") or []),
            "document_drafts": list(structured.get("document_drafts") or []),
            "source_count": len(answer.get("source_refs") or [])}


class OfficeView:
    def __init__(self, store: WorkspaceStore, *, limit: int) -> None:
        self._s = store
        self._limit = limit

    async def snapshot(self, viewer_id: object, now: datetime) -> dict[str, Any]:
        rows = await self._s.agent_tasks(int(INPUT_WAIT_MAX.total_seconds()))
        by_role: dict[str, list[AgentTaskRow]] = defaultdict(list)
        for r in rows:
            by_role[r.agent_role_key].append(r)
        # Agent kartasi uchun: joriy foydalanuvchining har agentdagi oxirgi yakunlangan vazifasi.
        last_mine: dict[str, AgentTaskRow] = {}
        for r in rows:
            if r.initiator_id == viewer_id and r.status in TERMINAL_TASK:
                if r.agent_role_key not in last_mine or r.updated_at > last_mine[
                        r.agent_role_key].updated_at:
                    last_mine[r.agent_role_key] = r
        answers = await self._s.answers([r.task_id for r in last_mine.values()])
        agents = []
        for role, (name, title) in AGENTS.items():
            tasks = by_role.get(role, [])
            positions = _positions(tasks)
            state, current = agent_state([_agent_task(r) for r in tasks], now)
            row = next((r for r in tasks if current and str(r.task_id) == current.task_id), None)
            active = [r for r in tasks if r.dispatched and r.status not in TERMINAL_TASK]
            agents.append({
                "role_key": role, "name": name, "title": title, "state": state.value,
                "partial": state is AgentState.COMPLETED and row is not None
                and row.status == "partial",
                "active_count": len(active), "limit": self._limit,
                "queue_length": len(positions),
                "current_task": None if row is None else task_view(
                    row, viewer_id, positions.get(row.task_id)),
                "tasks": [task_view(r, viewer_id, positions.get(r.task_id)) for r in tasks
                          if r.status not in TERMINAL_TASK][:10],
                "last_result": _result(last_mine.get(role), answers, viewer_id),
            })
        return {"agents": agents, "idle_after_seconds": int(IDLE_AFTER.total_seconds()),
                "generated_at": now.isoformat()}

    async def my_tasks(self, viewer_id: Any, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self._s.list_tasks(viewer_id, limit)
        out = []
        for r in rows:
            position = (await self._s.queue_position(r.task_id)
                        if not r.dispatched and r.status == "queued" else None)
            name, title = AGENTS.get(r.agent_role_key, (r.agent_role_key, ""))
            out.append({**task_view(r, viewer_id, position), "agent_name": name,
                        "agent_title": title})
        return out
