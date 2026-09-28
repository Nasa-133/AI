"""TZ 13.12: AI’ga ketadigan kontekstda shaxsiy ma’lumot psevdonimlanadi, javobda tiklanadi."""

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from business.platform.db import tenant_transaction

from .test_agent_queue import agent_event
from .test_documents import owner
from .test_identity_http import csrf

pytestmark = pytest.mark.integration

PHONE = "+998 90 123 45 67"


async def run_agent_instruction(engine: AsyncEngine, tenant: object, task_id: str) -> str:
    async with tenant_transaction(engine, tenant_id=tenant, user_id=None) as conn:  # type: ignore[arg-type]
        return str((await conn.execute(text(
            "SELECT envelope->'payload'->>'sanitized_instruction' FROM messaging.outbox"
            " WHERE event_type = 'RunAgent.v1' AND envelope->'payload'->>'task_id' = :t"),
            {"t": task_id})).scalar_one())


async def test_instruction_masked_and_answer_restored(client: httpx.AsyncClient,
                                                      app_engine: AsyncEngine) -> None:
    async with owner(client, "Maxfiy MChJ") as (c, tenant):
        assert (await c.get("/api/v1/privacy")).json() == {"pseudonymize": True,
                                                            "mask_customer_names": True}
        conv = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        url = f"/api/v1/conversations/{conv}/messages"
        sent = (await c.post(url, headers=csrf(c), json={
            "content": f"Ali, {PHONE} raqamli mijozning savdosi qancha?"})).json()
        instruction = await run_agent_instruction(app_engine, tenant, sent["task_id"])
        assert PHONE not in instruction and "[TEL-" in instruction  # modelga raqam ketmaydi
        token = instruction[instruction.index("[TEL-"):instruction.index("]") + 1]

        # Chat tarixida foydalanuvchi o‘z matnini asl holida ko‘radi.
        assert (await c.get(url)).json()[0]["content"].startswith(f"Ali, {PHONE}")
        step = (await c.get(f"/api/v1/tasks/{sent['task_id']}")).json()["steps"][0]["id"]
        await agent_event(client, app_engine, tenant, "completed", {
            "task_id": sent["task_id"], "task_step_id": step, "agent_run_id": str(uuid4()),
            "status": "succeeded", "source_refs": [], "error_code": None,
            "limitations": [f"{token} bo‘yicha ma’lumot kam"],
            "result_candidate": {"kind": "answer", "structured": None,
                                 "answer_markdown": f"{token} mijozining savdosi: 100 so‘m"},
            "usage": {"input_tokens": 0, "output_tokens": 0, "cost_estimate": "0",
                      "currency": "USD"}})
        answer = (await c.get(url)).json()[-1]
        assert answer["content"] == f"{PHONE} mijozining savdosi: 100 so‘m"
        task = (await c.get(f"/api/v1/tasks/{sent['task_id']}")).json()
        assert task["limitations"] == [f"{PHONE} bo‘yicha ma’lumot kam"]

        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=None) as conn:
            stored = (await conn.execute(text(
                "SELECT value_enc FROM governance.pii_tokens WHERE token = :t"),
                {"t": token})).scalar_one()
        assert PHONE not in stored  # vault’da shifrlangan


async def test_owner_can_disable_and_others_cannot(client: httpx.AsyncClient,
                                                   app_engine: AsyncEngine) -> None:
    async with owner(client, "Ochiq MChJ") as (c, tenant):
        r = await c.put("/api/v1/privacy", headers=csrf(c),
                        json={"pseudonymize": False, "mask_customer_names": False})
        assert r.status_code == 200 and r.json()["pseudonymize"] is False
        conv = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        sent = (await c.post(f"/api/v1/conversations/{conv}/messages", headers=csrf(c),
                             json={"content": f"Ali, {PHONE} savdosi"})).json()
        assert PHONE in await run_agent_instruction(app_engine, tenant, sent["task_id"])
        actions = [e["action"] for e in (await c.get("/api/v1/audit")).json()]
        assert "privacy.updated" in actions  # sozlama o‘zgarishi auditda
