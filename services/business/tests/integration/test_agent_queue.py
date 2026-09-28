"""T01: agent parallel limiti va navbat; ofis holati; navbatdagi vazifani bekor qilish (T05)."""

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from business.contexts.workspace.adapters.sql import SqlWorkspaceStore
from business.contexts.workspace.application.agent_events import AgentEventHandler
from business.entrypoints.wiring import task_dispatcher
from business.platform.db import tenant_transaction

from .test_documents import owner
from .test_identity_http import csrf

pytestmark = pytest.mark.integration


class _AllRefs:
    async def exists(self, query_id: UUID) -> bool:
        return True


async def run_agent_count(engine: AsyncEngine, tenant: UUID, task_ids: list[str]) -> int:
    async with tenant_transaction(engine, tenant_id=tenant, user_id=None) as conn:
        return int((await conn.execute(text(
            "SELECT count(*) FROM messaging.outbox WHERE event_type = 'RunAgent.v1'"
            " AND envelope->'payload'->>'task_id' = ANY(:ids)"), {"ids": task_ids})).scalar_one())


async def agent_event(client: httpx.AsyncClient, engine: AsyncEngine, tenant: UUID,
                      kind: str, payload: dict[str, Any]) -> None:
    container = client._transport.app.state.container  # type: ignore[attr-defined]
    async with tenant_transaction(engine, tenant_id=tenant, user_id=None) as conn:
        handler = AgentEventHandler(SqlWorkspaceStore(conn, tenant), _AllRefs(),
                                    task_dispatcher(container, conn, tenant))
        await getattr(handler, kind)(payload)


def agents(office: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {a["role_key"]: a for a in office["agents"]}


async def test_t01_queue_per_agent_and_office_state(client: httpx.AsyncClient,
                                                    app_engine: AsyncEngine) -> None:
    container = client._transport.app.state.container  # type: ignore[attr-defined]
    container.settings.agent_parallel_limit = 1
    try:
        async with owner(client, "Navbat MChJ") as (c, tenant):
            conv = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
            url = f"/api/v1/conversations/{conv}/messages"
            sent = [(await c.post(url, headers=csrf(c), json={"content": f"Ali, savdo {i}"})).json()
                    for i in range(3)]
            assert [s["queue_position"] for s in sent] == [None, 1, 2]
            ids = [s["task_id"] for s in sent]
            assert await run_agent_count(app_engine, tenant, ids) == 1

            # Boshqa mutaxassislik band emas — lekin savdo ishlari unga o‘tkazilmaydi (T01).
            other = (await c.post(url, headers=csrf(c),
                                  json={"content": "Madina, foyda qancha?"})).json()
            assert other["agent_role_key"] == "finance_analyst" and other["queue_position"] is None

            office = agents((await c.get("/api/v1/office")).json())
            ali = office["sales_analyst"]
            assert (ali["state"], ali["active_count"], ali["limit"], ali["queue_length"]) == (
                "queued", 1, 1, 2)
            assert ali["current_task"]["title"] == "Ali, savdo 0" and ali["current_task"]["mine"]
            assert office["document_assistant"]["state"] == "idle"
            detail = (await c.get(f"/api/v1/tasks/{ids[2]}")).json()
            assert detail["queue_position"] == 2

            step = (await c.get(f"/api/v1/tasks/{ids[0]}")).json()["steps"][0]["id"]
            run_id = str(uuid4())
            await agent_event(client, app_engine, tenant, "progressed", {
                "task_id": ids[0], "task_step_id": step, "agent_run_id": run_id,
                "phase": "retrieving", "message": "x", "tool_calls_used": 1, "sequence": 1})
            assert agents((await c.get("/api/v1/office")).json())["sales_analyst"][
                "state"] == "reading"

            await agent_event(client, app_engine, tenant, "completed", {
                "task_id": ids[0], "task_step_id": step, "agent_run_id": run_id,
                "status": "succeeded", "source_refs": [], "limitations": [], "error_code": None,
                "result_candidate": {"kind": "answer", "answer_markdown": "Tayyor",
                                     "structured": None},
                "usage": {"input_tokens": 0, "output_tokens": 0, "cost_estimate": "0",
                          "currency": "USD"}})
            # Slot bo‘shadi → navbatdagi birinchisi yuborildi, uchinchisi endi 1-o‘rinda.
            assert await run_agent_count(app_engine, tenant, ids) == 2
            assert (await c.get(f"/api/v1/tasks/{ids[2]}")).json()["queue_position"] == 1
            ali = agents((await c.get("/api/v1/office")).json())["sales_analyst"]
            assert (ali["active_count"], ali["queue_length"]) == (1, 1)
            # Agent kartasi: oxirgi natija (javob matni bilan).
            assert ali["last_result"]["id"] == ids[0] and ali["last_result"]["answer"] == "Tayyor"

            # T05: navbatdagi vazifa darhol bekor qilinadi, AI’ga hech narsa yuborilmaydi.
            r = await c.post(f"/api/v1/tasks/{ids[2]}/cancel", headers=csrf(c))
            assert r.status_code == 202
            assert (await c.get(f"/api/v1/tasks/{ids[2]}")).json()["status"] == "cancelled"
            assert await run_agent_count(app_engine, tenant, ids) == 2

            tasks = {t["id"]: t for t in (await c.get("/api/v1/tasks")).json()}
            assert tasks[ids[0]]["status"] == "succeeded" and tasks[ids[2]]["status"] == "cancelled"
            assert tasks[ids[1]]["agent_name"] == "Ali"
    finally:
        container.settings.agent_parallel_limit = 3


async def test_clarification_shows_awaiting_input_until_answered(
        client: httpx.AsyncClient, app_engine: AsyncEngine) -> None:
    async with owner(client, "Savol MChJ") as (c, tenant):
        conv = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        url = f"/api/v1/conversations/{conv}/messages"
        task = (await c.post(url, headers=csrf(c), json={"content": "Madina, foyda?"})).json()
        step = (await c.get(f"/api/v1/tasks/{task['task_id']}")).json()["steps"][0]["id"]
        await agent_event(client, app_engine, tenant, "completed", {
            "task_id": task["task_id"], "task_step_id": step, "agent_run_id": str(uuid4()),
            "status": "partial", "source_refs": [], "error_code": "CLARIFICATION_REQUIRED",
            "limitations": ["Aniqlashtiruvchi savolga javob kerak"],
            "result_candidate": {"kind": "answer", "answer_markdown": "Qaysi foyda?",
                                 "structured": None},
            "usage": {"input_tokens": 0, "output_tokens": 0, "cost_estimate": "0",
                      "currency": "USD"}})
        madina = agents((await c.get("/api/v1/office")).json())["finance_analyst"]
        assert madina["state"] == "awaiting_input"
        # Boshqa agentga xabar Madinaning savoliga javob emas.
        await c.post(url, headers=csrf(c), json={"content": "Ali, savdo qancha?"})
        madina = agents((await c.get("/api/v1/office")).json())["finance_analyst"]
        assert madina["state"] == "awaiting_input"
        await c.post(url, headers=csrf(c), json={"content": "Madina, yalpi foyda"})
        madina = agents((await c.get("/api/v1/office")).json())["finance_analyst"]
        assert madina["state"] == "queued"  # javob berildi — yangi vazifa navbatda/yuborilgan
