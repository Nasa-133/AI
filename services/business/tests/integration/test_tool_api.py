"""Tool API: servis tokeni, capability, joriy rol, siyosat, schema, idempotentlik (TZ 12, 13.12)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.platform.capability import Capability, CapabilitySigner
from business.platform.db import tenant_transaction

from .conftest import CAPABILITY_KEY, TOOLS_TOKEN
from .test_analytics import load_golden
from .test_identity_http import new_client, onboard

pytestmark = pytest.mark.integration
ALL_TOOLS = ("list_available_metrics", "run_metric_query", "compare_periods",
             "explain_contributions", "create_dashboard")


async def setup_tenant(client: httpx.AsyncClient, engine: AsyncEngine) -> tuple[UUID, UUID]:
    async with new_client(client) as c:
        _, body = await onboard(c, "Tool MChJ")
    tenant, user = UUID(body["tenant_id"]), UUID(body["user_id"])
    async with tenant_transaction(engine, tenant_id=tenant, user_id=user) as conn:
        await load_golden(SqlAnalyticsStore(conn, tenant), uuid4())
    return tenant, user


def capability(tenant: UUID, user: UUID, *, tools: tuple[str, ...] = ALL_TOOLS,
               ttl: timedelta = timedelta(minutes=10), task: UUID | None = None) -> str:
    return CapabilitySigner(CAPABILITY_KEY).issue(Capability(
        task or uuid4(), tenant, user, "sales_analyst", tools, datetime.now(UTC) + ttl))


async def call(client: httpx.AsyncClient, tool: str, args: dict[str, Any], cap: str,
               call_id: str = "call_1", token: str = TOOLS_TOKEN) -> httpx.Response:
    return await client.post(f"/internal/v1/tools/{tool}",
                             json={"tool_call_id": call_id, "arguments": args},
                             headers={"Authorization": f"Bearer {token}",
                                      "X-ABO-Capability": cap})


QUERY = {"metric_ids": ["net_sales", "gross_profit", "gross_margin"],
         "date_range": {"from": "2026-01-01", "to": "2026-01-31"}, "dimensions": [],
         "filters": {"branch_codes": None, "product_codes": None, "customer_codes": None},
         "currency": None, "limit": None}


async def test_auth_and_policy(client: httpx.AsyncClient, app_engine: AsyncEngine) -> None:
    tenant, user = await setup_tenant(client, app_engine)
    cap = capability(tenant, user)
    args = {"subject": "sales"}
    assert (await call(client, "list_available_metrics", args, cap, token="x" * 40)).status_code == 401
    assert (await call(client, "list_available_metrics", args, cap + "x")).status_code == 403
    expired = capability(tenant, user, ttl=timedelta(seconds=-1))
    assert (await call(client, "list_available_metrics", args, expired)).status_code == 403
    narrow = capability(tenant, user, tools=("list_available_metrics",))
    assert (await call(client, "run_metric_query", QUERY, narrow)).status_code == 403
    stranger = capability(tenant, uuid4())  # a’zo emas — delegation yo‘q
    assert (await call(client, "list_available_metrics", args, stranger)).status_code == 403
    other_tenant = capability(uuid4(), user)
    assert (await call(client, "list_available_metrics", args, other_tenant)).status_code == 403


async def test_query_results_and_errors(client: httpx.AsyncClient,
                                        app_engine: AsyncEngine) -> None:
    tenant, user = await setup_tenant(client, app_engine)
    cap = capability(tenant, user)
    listed = (await call(client, "list_available_metrics", {"subject": "all"}, cap)).json()
    assert listed["status"] == "ok" and listed["data"]["timezone"] == "Asia/Tashkent"
    assert listed["data"]["data_coverage"] == {"from": "2026-01-10", "to": "2026-04-05"}

    r = (await call(client, "run_metric_query", QUERY, cap, "call_2")).json()
    assert r["status"] == "ok" and r["data"]["rows"] == [["850.00", "350.00", "41.18"]]
    assert any(ref["kind"] == "query_result" for ref in r["source_refs"])

    bad = (await call(client, "run_metric_query", {**QUERY, "metric_ids": []}, cap, "c3")).json()
    assert bad["status"] == "error" and bad["error_code"] == "INVALID_ARGUMENTS"
    unknown = (await call(client, "run_metric_query", {**QUERY, "metric_ids": ["net_profit"]},
                          cap, "c4")).json()
    assert unknown["error_code"] == "UNKNOWN_METRIC"


async def test_create_dashboard_is_idempotent(client: httpx.AsyncClient,
                                              app_engine: AsyncEngine) -> None:
    tenant, user = await setup_tenant(client, app_engine)
    task = uuid4()
    cap = capability(tenant, user, task=task)
    q = (await call(client, "run_metric_query", {**QUERY, "dimensions": ["month"],
                                                 "date_range": {"from": "2026-01-01",
                                                                "to": "2026-04-30"}},
                    cap, "q1")).json()["data"]
    widgets = [{"title": "Oylar bo‘yicha", "type": "line", "query_spec_id": q["query_spec_id"],
                "text": None}]
    args = {"title": "Savdo dinamikasi", "description": None, "widgets": widgets}
    first = (await call(client, "create_dashboard", args, cap, "d1")).json()
    again = (await call(client, "create_dashboard", args, cap, "d1")).json()
    assert first["status"] == "ok" and first == again
    other = (await call(client, "create_dashboard", args, cap, "d2")).json()
    assert other["data"]["dashboard_id"] != first["data"]["dashboard_id"]

    kpi = {**args, "widgets": [{**widgets[0], "type": "kpi"}]}
    wrong = (await call(client, "create_dashboard", kpi, cap, "d3")).json()
    assert wrong["status"] == "error" and wrong["error_code"] == "INVALID_DASHBOARD"
    fake = {**args, "widgets": [{**widgets[0], "query_spec_id": str(uuid4())}]}
    assert (await call(client, "create_dashboard", fake, cap, "d4")).json()["status"] == "error"
    # Audit: agent yaratgan ikki dashboard (takroriy chaqiruv va xatolar yozilmaydi).
    async with tenant_transaction(app_engine, tenant_id=tenant, user_id=None) as conn:
        rows = (await conn.execute(text(
            "SELECT actor_kind, actor_id, target_id FROM governance.audit_events"
            " WHERE action = 'agent.dashboard_created'"))).all()
    assert [(r.actor_kind, r.actor_id, r.target_id) for r in rows] == [
        ("agent", user, str(task))] * 2


async def test_settings_not_approved_is_reported(client: httpx.AsyncClient,
                                                 app_engine: AsyncEngine) -> None:
    async with new_client(client) as c:
        _, body = await onboard(c, "Yangi MChJ")
    cap = capability(UUID(body["tenant_id"]), UUID(body["user_id"]))
    r = (await call(client, "run_metric_query", QUERY, cap)).json()
    assert r["error_code"] == "METRIC_SETTINGS_NOT_APPROVED"


async def test_document_tools(client: httpx.AsyncClient, app_engine: AsyncEngine,
                              tmp_path: Any) -> None:
    from tests.unit.documents.samples import make_docx

    from .test_documents import process, upload
    from .test_identity_http import complete_mfa

    async with new_client(client) as c:
        _, body = await onboard(c, "Hujjat vosita MChJ")
        await complete_mfa(c)
        tenant, user = UUID(body["tenant_id"]), UUID(body["user_id"])
        doc = await upload(c, make_docx(tmp_path / "Shartnoma.docx"))
        await process(client, app_engine, tenant, doc)

    cap = CapabilitySigner(CAPABILITY_KEY).issue(Capability(
        uuid4(), tenant, user, "document_assistant",
        ("search_documents", "read_document_section", "create_document_draft"),
        datetime.now(UTC) + timedelta(minutes=5)))
    found = (await call(client, "search_documents",
                        {"query": "to‘lov muddati", "document_ids": None, "limit": 3}, cap)).json()
    assert found["status"] == "ok" and found["data"]["results"]
    ref = found["source_refs"][0]
    assert ref["kind"] == "document_version" and ref["version_id"] == doc["version_id"]

    section = (await call(client, "read_document_section", {
        "document_id": doc["id"], "version_id": doc["version_id"], "section_id": "p2"},
        cap, "c2")).json()
    assert section["data"]["text"].startswith("To‘lov 15 kun")

    draft = (await call(client, "create_document_draft", {
        "document_id": doc["id"], "base_version_id": doc["version_id"],
        "expected_version_id": doc["version_id"], "comment": None,
        "operations": [{"op": "replace_text", "section_id": "p2", "find": "15 kun",
                        "replace": "30 kun", "occurrence": 1}]}, cap, "c3")).json()
    assert draft["status"] == "ok" and draft["data"]["version_no"] == 2

    # Sales analitik agentiga hujjat tahriri berilmagan (siyosat).
    sales = CapabilitySigner(CAPABILITY_KEY).issue(Capability(
        uuid4(), tenant, user, "sales_analyst", ("create_document_draft",),
        datetime.now(UTC) + timedelta(minutes=5)))
    denied = await call(client, "create_document_draft", {
        "document_id": doc["id"], "base_version_id": doc["version_id"],
        "expected_version_id": doc["version_id"], "comment": None, "operations": [
            {"op": "replace_text", "section_id": "p2", "find": "15", "replace": "9",
             "occurrence": 1}]}, sales, "c4")
    assert denied.status_code == 403
