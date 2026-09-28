"""TZ 19: budjet rezervi, limitda yangi pulli ish to‘xtaydi, sarf yakunlanadi, 80% ogohlantirish."""

from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from .test_agent_queue import agent_event
from .test_documents import owner
from .test_identity_http import csrf

pytestmark = pytest.mark.integration


def completed(task_id: str, step: str, cost: str) -> dict[str, object]:
    return {"task_id": task_id, "task_step_id": step, "agent_run_id": str(uuid4()),
            "status": "succeeded", "source_refs": [], "limitations": [], "error_code": None,
            "result_candidate": {"kind": "answer", "answer_markdown": "ok", "structured": None},
            "usage": {"input_tokens": 1000, "output_tokens": 200, "cost_estimate": cost,
                      "currency": "USD"}}


async def test_budget_reserve_settle_and_block(client: httpx.AsyncClient,
                                               app_engine: AsyncEngine) -> None:
    async with owner(client, "Budjet MChJ") as (c, tenant):
        b = (await c.get("/api/v1/budget")).json()
        assert (b["monthly_limit"], b["state"], b["reservation_per_task"]) == ("50.00", "ok", "0.05")
        r = await c.put("/api/v1/budget", headers=csrf(c),
                        json={"daily_limit": None, "monthly_limit": "0.95"})
        assert r.status_code == 200 and r.json()["monthly_limit"] == "0.95"

        conv = (await c.post("/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        url = f"/api/v1/conversations/{conv}/messages"
        first = (await c.post(url, headers=csrf(c), json={"content": "Ali, savdo"})).json()
        assert (await c.get("/api/v1/budget")).json()["spent_month"] == "0.05"  # ochiq rezerv
        step = (await c.get(f"/api/v1/tasks/{first['task_id']}")).json()["steps"][0]["id"]
        await agent_event(client, app_engine, tenant, "completed",
                          completed(first["task_id"], step, "0.850000"))
        b = (await c.get("/api/v1/budget")).json()
        assert (b["spent_month"], b["state"], b["percent"]) == ("0.85", "warning", 89)

        # 0.85 + 0.05 = 0.90 va + 0.05 = 0.95 — limit ichida; uchinchisi oshadi, AI’ga yuborilmaydi.
        second = (await c.post(url, headers=csrf(c), json={"content": "Ali, savdo 2"})).json()
        third = (await c.post(url, headers=csrf(c), json={"content": "Ali, savdo 3"})).json()
        fourth = (await c.post(url, headers=csrf(c), json={"content": "Ali, savdo 4"})).json()
        statuses = [(await c.get(f"/api/v1/tasks/{t['task_id']}")).json() for t in
                    (second, third, fourth)]
        assert [s["status"] for s in statuses] == ["queued", "queued", "failed"]
        assert statuses[2]["error_code"] == "BUDGET_EXCEEDED"
        messages = (await c.get(url)).json()
        assert any("budjeti limiti tugagan" in m["content"] for m in messages)
        assert (await c.get("/api/v1/budget")).json()["state"] == "exceeded"


async def test_only_owner_changes_budget(client: httpx.AsyncClient) -> None:
    async with owner(client, "Budjet2 MChJ") as (c, _):
        r = await c.put("/api/v1/budget", headers=csrf(c), json={"monthly_limit": "-1"})
        assert r.status_code == 422
