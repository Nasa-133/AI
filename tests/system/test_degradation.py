"""Degradatsiya (TZ I03, I05, 13.15 gate 5/7) — scripts/degradation.sh bosqichma-bosqich chaqiradi.

Bosqichlar orasida holat (sessiya cookie’si, vazifa va hujjat ID’lari) faylda saqlanadi.
"""

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from test_vertical_slice import BASE, GOLDEN, contract_docx, csrf, register, until

pytestmark = pytest.mark.system
STATE = Path(os.environ.get("DEGRADATION_STATE", "/tmp/abo-degradation.json"))  # noqa: S108
PHASE = os.environ.get("DEGRADATION_PHASE", "")
TERMINAL = {"succeeded", "partial", "failed", "cancelled"}


def only(phase: str) -> pytest.MarkDecorator:
    return pytest.mark.skipif(PHASE != phase, reason=f"faqat {phase} bosqichida")


def save(c: httpx.AsyncClient, **data: Any) -> None:
    old = json.loads(STATE.read_text()) if STATE.exists() else {}
    STATE.write_text(json.dumps({**old, **data, "cookies": dict(c.cookies)}))


def load() -> dict[str, Any]:
    return dict(json.loads(STATE.read_text()))


def client(state: dict[str, Any] | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30, cookies=(state or {}).get("cookies"))


async def post_message(c: httpx.AsyncClient, conv: str, text: str) -> str:
    r = await c.post(f"{BASE}/api/v1/conversations/{conv}/messages", headers=csrf(c),
                     json={"content": text})
    assert r.status_code == 202, r.text
    return str(r.json()["task_id"])


async def agent_messages(c: httpx.AsyncClient, conv: str, task: str) -> list[dict[str, Any]]:
    messages = (await c.get(f"{BASE}/api/v1/conversations/{conv}/messages")).json()
    return [m for m in messages if m["task_id"] == task and m["author_kind"] == "agent"]


@only("ai_down")
async def test_i05_ai_down_search_falls_back_and_task_waits(tmp_path: Path) -> None:
    STATE.unlink(missing_ok=True)
    async with client() as c:
        await register(c, "Degradatsiya MChJ")
        path = contract_docx(tmp_path / "Shartnoma.docx")
        with path.open("rb") as f:
            doc = (await c.post(f"{BASE}/api/v1/documents", headers=csrf(c),
                                files={"file": (path.name, f)})).json()["id"]

        async def parsed() -> bool:
            v = (await c.get(f"{BASE}/api/v1/documents/{doc}")).json()["versions"][0]
            return v["parse_status"] == "ready"

        await until(parsed, "parse (AI’siz ham)")
        found = (await c.post(f"{BASE}/api/v1/documents/search", headers=csrf(c),
                              json={"query": "to‘lov muddati"})).json()
        assert found["mode"] == "full_text" and found["notes"], found  # I05: matnli rejim
        assert "30 kun" in found["results"][0]["text"]

        conv = (await c.post(f"{BASE}/api/v1/conversations", headers=csrf(c), json={})).json()["id"]
        task = await post_message(c, conv, "Ali, savdo qancha?")
        await until(lambda: _sleep_ok(3), "kutish", timeout=10)
        detail = (await c.get(f"{BASE}/api/v1/tasks/{task}")).json()
        assert detail["status"] == "queued"  # aniq holat — navbatda
        assert await agent_messages(c, conv, task) == []  # soxta javob yo‘q
        assert (await c.get(f"{BASE}/api/v1/dashboards")).status_code == 200  # ko‘rish ishlaydi
        ali = next(a for a in (await c.get(f"{BASE}/api/v1/office")).json()["agents"]
                   if a["role_key"] == "sales_analyst")
        assert ali["state"] == "queued"
        save(c, conv=conv, task=task, doc=doc)


async def _sleep_ok(seconds: float) -> bool:
    import asyncio
    await asyncio.sleep(seconds)
    return True


@only("ai_up")
async def test_i05_ai_recovers_task_runs_once_and_embeddings_arrive() -> None:
    state = load()
    async with client(state) as c:
        async def finished() -> dict[str, Any] | None:
            t = (await c.get(f"{BASE}/api/v1/tasks/{state['task']}")).json()
            return t if t["status"] in TERMINAL else None

        task = await until(finished, "AI tiklangach vazifa bajarilishi", timeout=60)
        assert task["status"] != "failed", task
        assert len(await agent_messages(c, state["conv"], state["task"])) == 1  # bir marta

        async def embedded() -> bool:
            v = (await c.get(f"{BASE}/api/v1/documents/{state['doc']}")).json()["versions"][0]
            return v["embedding_status"] == "ready"

        await until(embedded, "embedding (AI tiklangach)", timeout=60)
        found = (await c.post(f"{BASE}/api/v1/documents/search", headers=csrf(c),
                              json={"query": "to‘lov muddati"})).json()
        assert found["mode"] == "hybrid"


@only("integration_down")
async def test_i03_integration_down_import_waits_dashboards_marked_stale() -> None:
    state = load()
    async with client(state) as c:
        with (GOLDEN / "sotuvlar.csv").open("rb") as f:
            upload = (await c.post(f"{BASE}/api/v1/uploads", headers=csrf(c),
                                   files={"file": ("sotuvlar.csv", f, "text/csv")},
                                   data={"purpose": "dataset_import"})).json()
        source = (await c.post(f"{BASE}/api/v1/integrations", headers=csrf(c), json={
            "connector_id": "file_import", "name": "sotuvlar.csv",
            "upload_id": upload["id"]})).json()["id"]

        async def stale() -> dict[str, Any] | None:
            f = (await c.get(f"{BASE}/api/v1/data-freshness")).json()
            return f if f["state"] == "stale" else None

        fresh = await until(stale, "dashboard “eskirgan” belgisi", timeout=30)
        assert fresh["waiting"][0]["id"] == source and "javob bermayapti" in fresh["message"]
        s = (await c.get(f"{BASE}/api/v1/integrations/{source}")).json()
        assert s["status"] == "discovering"  # import “kutilmoqda”, yo‘qolmagan

        # Chat va hujjatlar ishlaydi (AI ishlayapti).
        task = await post_message(c, state["conv"], f"Ali, savdo {uuid4().hex[:4]}")

        async def done() -> bool:
            t = (await c.get(f"{BASE}/api/v1/tasks/{task}")).json()
            return t["status"] in TERMINAL

        await until(done, "chat Integration’siz", timeout=60)
        found = (await c.post(f"{BASE}/api/v1/documents/search", headers=csrf(c),
                              json={"query": "penya"})).json()
        assert found["results"]


@only("broker_down")
async def test_broker_down_task_is_saved_and_visible() -> None:
    state = load()
    async with client(state) as c:
        task = await post_message(c, state["conv"], "Ali, broker o‘chiq paytidagi savol")
        detail = (await c.get(f"{BASE}/api/v1/tasks/{task}")).json()
        assert detail["status"] == "queued"  # gate 7: pending task ko‘rinadi
        save(c, broker_task=task)


@only("broker_up")
async def test_broker_restart_task_completes_once() -> None:
    state = load()
    async with client(state) as c:
        async def finished() -> dict[str, Any] | None:
            t = (await c.get(f"{BASE}/api/v1/tasks/{state['broker_task']}")).json()
            return t if t["status"] in TERMINAL else None

        task = await until(finished, "broker qayta ishga tushgach vazifa", timeout=90)
        assert task["status"] != "failed", task
        assert len(await agent_messages(c, state["conv"], state["broker_task"])) == 1
