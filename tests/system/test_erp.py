"""ERP REST API orqali to‘liq oqim — haqiqiy jarayonlar bilan (scripts/e2e.sh soxta ERP’ni ham
ishga tushiradi): ERP ulash → mapping tasdiqlash → sinxron → agentlar ERP ma’lumotidan javob beradi."""

import re
from typing import Any

import httpx
import pytest

from test_vertical_slice import BASE, ask, csrf, register, until

pytestmark = pytest.mark.system

ERP_OBJECTS = {"sales.order_line": "ERP: Sotuvlar", "sales.return": "ERP: Qaytarishlar",
               "finance.receivable": "ERP: Debitorlik"}


async def connect(c: httpx.AsyncClient, entity: str, name: str) -> str:
    r = await c.post(f"{BASE}/api/v1/integrations", headers=csrf(c),
                     json={"connector_id": "erp_api", "name": name, "entity": entity})
    assert r.status_code == 202, r.text
    source = r.json()["id"]

    async def source_in(*states: str) -> dict[str, Any] | None:
        s = (await c.get(f"{BASE}/api/v1/integrations/{source}")).json()
        assert s["status"] != "failed", s
        return s if s["status"] in states else None

    discovered = await until(lambda: source_in("awaiting_mapping"), f"{name}: discover")
    assert discovered["entity"] == entity
    # Bir resurs boshqa obyekt shabloniga ham qisman mos kelishi mumkin — UI kabi eng mosi olinadi.
    proposal = max((e for e in discovered["discovery"]["entities"] if e["entity"] == entity),
                   key=lambda e: e["match_score"])
    assert proposal["match_score"] == 1.0 and not proposal["unmapped_required_fields"]
    status_map = [{"source_value": k, "canonical_value": v}
                  for k, v in proposal["status_map"].items()] if proposal.get("status_map") else [
        {"source_value": k, "canonical_value": v} for k, v in
        {"posted": "confirmed", "draft": "draft", "cancelled": "cancelled"}.items()]
    r = await c.post(f"{BASE}/api/v1/integrations/{source}/mapping", headers=csrf(c),
                     json={"entity": entity, "mapping": proposal["suggested_mapping"],
                           "status_map": status_map})
    assert r.status_code == 202, r.text
    await until(lambda: source_in("ready"), f"{name}: mapping")
    assert (await c.post(f"{BASE}/api/v1/integrations/{source}/sync",
                         headers=csrf(c))).status_code == 202
    await until(lambda: source_in("synced"), f"{name}: sync", timeout=180)
    return source


async def test_erp_api_to_agent_answers() -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        await register(c, "ERP E2E MChJ")
        assert (await c.post(f"{BASE}/api/v1/metric-settings/approve", headers=csrf(c),
                             json={})).status_code == 200
        for entity, name in ERP_OBJECTS.items():
            await connect(c, entity, name)

        conv = (await c.post(f"{BASE}/api/v1/conversations", headers=csrf(c),
                             json={"title": "ERP"})).json()["id"]
        # Sentabr 2026 — demo tarixidan keyin: faqat ERP’ning “jonli” hujjatlaridan.
        sales = await ask(c, conv, "Ali, 2026 sentabr oyidagi savdoni filiallar bo‘yicha ko‘rsat")
        assert sales["task"]["status"] == "succeeded", sales
        assert re.search(r"\d", sales["answer"]["content"]), sales["answer"]["content"]
        assert {r["kind"] for r in sales["answer"]["source_refs"]} >= {"dataset_snapshot",
                                                                       "query_result"}
        debt = await ask(c, conv, "Madina, 2026 avgust oxiridagi debitorlik qoldig‘i qancha?")
        assert debt["task"]["status"] == "succeeded", debt
        assert re.search(r"\d", debt["answer"]["content"]), debt["answer"]["content"]
