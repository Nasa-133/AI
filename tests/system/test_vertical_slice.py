"""Bosqich 1 vertikal kesimi — haqiqiy jarayonlar bilan (scripts/e2e.sh ishga tushiradi).

CSV yuklash → mapping tasdiqlash → sync → ingestion → chat savoli → AI (FakeProvider) →
Tool API → deterministik hisob → manbali javob → dashboard. Faqat public HTTP API orqali.
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pyotp
import pytest

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8000")
GOLDEN = Path(__file__).resolve().parents[2] / "fixtures/synthetic/golden"
pytestmark = pytest.mark.system


async def until(check: Callable[[], Awaitable[Any]], what: str, timeout: float = 60) -> Any:
    async with asyncio.timeout(timeout):
        while True:
            if result := await check():
                return result
            await asyncio.sleep(0.5)  # noqa: ASYNC110 — tashqi jarayonlar holati kutiladi
    raise AssertionError(what)


def csrf(c: httpx.AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("abo_csrf") or ""}


async def import_file(c: httpx.AsyncClient, name: str) -> None:
    with (GOLDEN / name).open("rb") as f:
        r = await c.post(f"{BASE}/api/v1/uploads", headers=csrf(c),
                         files={"file": (name, f, "text/csv")}, data={"purpose": "dataset_import"})
    assert r.status_code == 201, r.text
    r = await c.post(f"{BASE}/api/v1/integrations", headers=csrf(c),
                     json={"connector_id": "file_import", "name": name, "upload_id": r.json()["id"]})
    source = r.json()["id"]

    async def source_in(*states: str) -> dict[str, Any] | None:
        s = (await c.get(f"{BASE}/api/v1/integrations/{source}")).json()
        assert s["status"] != "failed", s
        return s if s["status"] in states else None

    discovered = await until(lambda: source_in("awaiting_mapping"), f"{name}: discover")
    best = discovered["discovery"]["entities"][0]
    assert best["match_score"] == 1.0 and not best["unmapped_required_fields"]
    status_map = [{"source_value": k, "canonical_value": v} for k, v in
                  {"tasdiqlangan": "confirmed", "qoralama": "draft",
                   "bekor qilingan": "cancelled"}.items()]
    r = await c.post(f"{BASE}/api/v1/integrations/{source}/mapping", headers=csrf(c),
                     json={"entity": best["entity"], "mapping": best["suggested_mapping"],
                           "status_map": status_map})
    assert r.status_code == 202, r.text
    await until(lambda: source_in("ready"), f"{name}: mapping qabul qilinishi")
    assert (await c.post(f"{BASE}/api/v1/integrations/{source}/sync", headers=csrf(c))).status_code == 202
    await until(lambda: source_in("synced"), f"{name}: sync")


async def ask(c: httpx.AsyncClient, conversation: str, text: str) -> dict[str, Any]:
    r = await c.post(f"{BASE}/api/v1/conversations/{conversation}/messages", headers={
        **csrf(c), "Idempotency-Key": str(uuid4())}, json={"content": text})
    assert r.status_code == 202, r.text
    task = r.json()["task_id"]
    events: list[str] = []
    async with c.stream("GET", f"{BASE}/api/v1/tasks/{task}/events", timeout=90) as stream:
        async for line in stream.aiter_lines():
            if line.startswith("event: "):
                events.append(line.removeprefix("event: "))
            if events and events[-1] == "task.completed" and line.startswith("data: "):
                break
    detail = (await c.get(f"{BASE}/api/v1/tasks/{task}")).json()
    messages = (await c.get(f"{BASE}/api/v1/conversations/{conversation}/messages")).json()
    answer = next(m for m in reversed(messages) if m["task_id"] == task and m["author_kind"] == "agent")
    return {"task": detail, "events": events, "answer": answer}


async def test_csv_to_answer_to_dashboard() -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/api/v1/tenants", json={
            "email": f"e2e-{uuid4().hex[:8]}@demo.uz", "password": "correct-horse-battery",
            "tenant_name": "E2E MChJ"})
        assert r.status_code == 201, r.text
        secret = (await c.post(f"{BASE}/api/v1/auth/mfa/enroll", headers=csrf(c))).json()["secret"]
        r = await c.post(f"{BASE}/api/v1/auth/mfa/verify", headers=csrf(c),
                         json={"code": pyotp.TOTP(secret).now()})
        assert r.status_code == 200, r.text
        assert (await c.post(f"{BASE}/api/v1/metric-settings/approve", headers=csrf(c),
                             json={})).status_code == 200

        await import_file(c, "sotuvlar.csv")
        await import_file(c, "qaytarishlar.csv")

        conv = (await c.post(f"{BASE}/api/v1/conversations", headers=csrf(c),
                             json={"title": "E2E"})).json()["id"]
        result = await ask(c, conv, "Ali, 2026 yanvar oyidagi savdoni ko‘rsat")
        assert result["task"]["status"] == "succeeded", result
        assert "task.progress" in result["events"]
        answer = result["answer"]
        assert "850" in answer["content"], answer["content"]  # A01: sof savdo 850.00
        assert {r["kind"] for r in answer["source_refs"]} >= {"dataset_snapshot", "query_result"}

        result = await ask(c, conv, "Ali, 2026 yanvar savdosini dashboard qil")
        assert result["task"]["status"] == "succeeded", result
        cards = (await c.get(f"{BASE}/api/v1/dashboards")).json()
        assert len(cards) == 1, cards
        detail = (await c.get(f"{BASE}/api/v1/dashboards/{cards[0]['id']}")).json()
        assert all(w["status"] == "ready" for w in detail["widgets"]), detail
