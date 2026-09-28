"""T01, T02, T04, T05: agent navbati, ofis holati, SSE qayta ulanish, idempotentlik, bekor qilish."""

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from business.contexts.workspace.adapters.sql import SqlWorkspaceStore
from business.contexts.workspace.application.agent_events import AgentEventHandler
from business.entrypoints.wiring import BudgetGateAdapter, PrivacyGateAdapter, task_dispatcher
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
                                    task_dispatcher(container, conn, tenant),
                                    BudgetGateAdapter(container, conn, tenant),
                                    PrivacyGateAdapter(container, conn, tenant))
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


def sse_events(body: str) -> list[tuple[int, str]]:
    out = []
    for block in body.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line
                      and not line.startswith(":"))
        if "id" in fields:
            out.append((int(fields["id"]), fields["event"]))
    return out


async def test_t02_sse_resumes_from_last_event_id_without_rerun(
    client: httpx.AsyncClient, app_engine: AsyncEngine,
) -> None:
    async with owner(client, "SSE MChJ") as (c, tenant):
        conv = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        task = (await c.post(f"/api/v1/conversations/{conv}/messages", headers=csrf(c),
                             json={"content": "Ali, savdo qancha?"})).json()["task_id"]
        step = (await c.get(f"/api/v1/tasks/{task}")).json()["steps"][0]["id"]
        run_id = str(uuid4())
        for seq, phase in enumerate(("retrieving", "calculating"), start=1):
            await agent_event(client, app_engine, tenant, "progressed", {
                "task_id": task, "task_step_id": step, "agent_run_id": run_id, "phase": phase,
                "message": phase, "tool_calls_used": seq, "sequence": seq})
        await agent_event(client, app_engine, tenant, "completed", {
            "task_id": task, "task_step_id": step, "agent_run_id": run_id,
            "status": "succeeded", "source_refs": [], "limitations": [], "error_code": None,
            "result_candidate": {"kind": "answer", "answer_markdown": "Tayyor",
                                 "structured": None},
            "usage": {"input_tokens": 0, "output_tokens": 0, "cost_estimate": "0",
                      "currency": "USD"}})

        url = f"/api/v1/tasks/{task}/events"
        full = sse_events((await c.get(url)).text)
        assert full[-1][1] == "task.completed" and len(full) >= 4
        assert [i for i, _ in full] == sorted(i for i, _ in full)  # tartib saqlanadi
        # Uzilish: mijoz 2-eventni oldi → qayta ulanishda faqat keyingilari, takrorsiz.
        cut = full[1][0]
        resumed = sse_events((await c.get(url, headers={"Last-Event-ID": str(cut)})).text)
        assert resumed == [e for e in full if e[0] > cut]
        # Qayta ulanish vazifani qayta ishga tushirmaydi (T02).
        assert await run_agent_count(app_engine, tenant, [task]) == 1
        assert (await c.get(f"/api/v1/tasks/{task}")).json()["status"] == "succeeded"


async def test_t04_same_idempotency_key_creates_one_task(
    client: httpx.AsyncClient, app_engine: AsyncEngine,
) -> None:
    async with owner(client, "Idem MChJ") as (c, tenant):
        conv = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        url = f"/api/v1/conversations/{conv}/messages"
        headers = {**csrf(c), "Idempotency-Key": f"msg-{uuid4()}"}
        first = await c.post(url, headers=headers, json={"content": "Ali, savdo qancha?"})
        again = await c.post(url, headers=headers, json={"content": "Ali, savdo qancha?"})
        assert first.status_code == again.status_code == 202
        assert first.json() == again.json()
        messages = (await c.get(url)).json()
        assert sum(1 for m in messages if m["author_kind"] == "user") == 1
        tasks = (await c.get("/api/v1/tasks")).json()
        assert [t["id"] for t in tasks] == [first.json()["task_id"]]
        assert await run_agent_count(app_engine, tenant, [first.json()["task_id"]]) == 1
        # Boshqa kalit — yangi vazifa.
        other = await c.post(url, headers={**csrf(c), "Idempotency-Key": f"msg-{uuid4()}"},
                             json={"content": "Ali, savdo qancha?"})
        assert other.json()["task_id"] != first.json()["task_id"]


async def test_follow_up_carries_masked_conversation(client: httpx.AsyncClient,
                                                     app_engine: AsyncEngine) -> None:
    """“Barchasi” kabi davom javobi oldingi savolsiz tushunilmaydi: RunAgent suhbatni olib boradi."""
    async with owner(client, "Davom MChJ") as (c, tenant):
        conv = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        url = f"/api/v1/conversations/{conv}/messages"
        first = (await c.post(url, headers=csrf(c), json={
            "content": "Madina, oylik hisobot bo‘yicha dashboard qur, tel +998901234567"})).json()
        step = (await c.get(f"/api/v1/tasks/{first['task_id']}")).json()["steps"][0]["id"]
        await agent_event(client, app_engine, tenant, "completed", {
            "task_id": first["task_id"], "task_step_id": step, "agent_run_id": str(uuid4()),
            "status": "partial", "source_refs": [], "limitations": [],
            "error_code": "CLARIFICATION_REQUIRED",
            "result_candidate": {"kind": "answer", "answer_markdown": "Qaysi ko‘rsatkich kerak?",
                                 "structured": None},
            "usage": {"input_tokens": 0, "output_tokens": 0, "cost_estimate": "0",
                      "currency": "USD"}})
        # Murojaatsiz “barchasi” — aniqlashtirish so‘ragan agentga (Madina) qaytadi.
        second = (await c.post(url, headers=csrf(c), json={"content": "barchasi"})).json()
        assert second["agent_role_key"] == "finance_analyst"

        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=None) as conn:
            payloads = {r[0]: r[1] for r in (await conn.execute(text(
                "SELECT envelope->'payload'->>'task_id', envelope->'payload'"
                " FROM messaging.outbox WHERE event_type = 'RunAgent.v1'"
                " AND envelope->'payload'->>'task_id' = ANY(:ids)"),
                {"ids": [first["task_id"], second["task_id"]]})).all()}
        assert payloads[first["task_id"]]["conversation"] == []
        turns = payloads[second["task_id"]]["conversation"]
        assert [(t["role"], t["agent_role_key"]) for t in turns] == [
            ("user", None), ("agent", "finance_analyst")]
        assert turns[1]["text"] == "Qaysi ko‘rsatkich kerak?"
        # AI’ga ketadigan tarix ham psevdonimlanadi (TZ 13.12).
        assert "+998901234567" not in turns[0]["text"] and "[TEL-" in turns[0]["text"]
