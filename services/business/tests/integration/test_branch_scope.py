"""S02: faqat bir filial ruxsati bor foydalanuvchi — HTTP so‘rov, Tool API, taqqoslash, dashboard."""

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.contexts.dashboards.adapters.sql import AnalyticsQueryResults, SqlDashboardStore
from business.contexts.dashboards.application.service import DashboardService
from business.platform.db import tenant_transaction
from tests.unit.identity.fakes import RecordingNotifier

from .test_analytics import load_golden
from .test_identity_http import PASSWORD, complete_mfa, csrf, new_client, onboard
from .test_tool_api import call, capability

pytestmark = pytest.mark.integration

JAN_APR = {"from": "2026-01-01", "to": "2026-04-30"}


def by_branch(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"metric_ids": ["net_sales"], "date_range": JAN_APR, "dimensions": ["branch"],
            "filters": filters or {}}


def tool_query(branches: list[str] | None = None) -> dict[str, Any]:
    """Tool API sxemasi barcha kalitlarni talab qiladi (strict)."""
    return {**by_branch({"branch_codes": branches, "product_codes": None,
                         "customer_codes": None}), "currency": None, "limit": None}


async def create_dashboard(engine: AsyncEngine, tenant: UUID, user: UUID, query_id: str) -> str:
    async with tenant_transaction(engine, tenant_id=tenant, user_id=user) as conn:
        service = DashboardService(SqlDashboardStore(conn, tenant),
                                   AnalyticsQueryResults(SqlAnalyticsStore(conn, tenant)))
        d = await service.create(user_id=user, task_id=None, title="Filiallar", description=None,
                                 widgets=[{"title": "Sof savdo", "type": "table",
                                           "query_spec_id": query_id, "text": None}])
    return str(d.id)


async def test_single_branch_user_sees_only_allowed_branch(
    client: httpx.AsyncClient, app_engine: AsyncEngine, notifier: RecordingNotifier
) -> None:
    email = f"bux-{uuid4().hex[:8]}@demo.uz"
    async with new_client(client) as owner, new_client(client) as analyst:
        _, body = await onboard(owner, "Filial MChJ")
        await complete_mfa(owner)
        tenant, owner_id = UUID(body["tenant_id"]), UUID(body["user_id"])
        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=owner_id) as conn:
            await load_golden(SqlAnalyticsStore(conn, tenant), uuid4())
        r = await owner.post("/api/v1/invitations", json={"email": email, "role": "analyst"},
                             headers=csrf(owner))
        token = next(t for e, t in notifier.invitations if e == email)
        r = await analyst.post("/api/v1/invitations/accept",
                               json={"token": token, "password": PASSWORD})
        analyst_id = UUID(r.json()["user_id"])

        # Doirani faqat Owner/Admin beradi; Owner’ga doira berilmaydi; bo‘sh ro‘yxat — xato.
        url = f"/api/v1/members/{analyst_id}/branches"
        r = await owner.put(url, json={"branch_codes": ["BUX", " BUX "]}, headers=csrf(owner))
        assert r.status_code == 200 and r.json()["branch_scope"] == ["BUX"], r.text
        assert (await analyst.put(url, json={"branch_codes": None},
                                  headers=csrf(analyst))).status_code == 403
        assert (await owner.put(f"/api/v1/members/{owner_id}/branches", json={
            "branch_codes": ["BUX"]}, headers=csrf(owner))).status_code == 403
        assert (await owner.put(url, json={"branch_codes": []},
                                headers=csrf(owner))).status_code == 422
        members = {m["user_id"]: m for m in (await owner.get("/api/v1/members")).json()}
        assert members[str(analyst_id)]["branch_scope"] == ["BUX"]

        # Umumiy so‘rov: faqat ruxsatli filial natijasi va cheklov izohi.
        r = await analyst.post("/api/v1/analytics/queries", json=by_branch(), headers=csrf(analyst))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert [row[0] for row in data["rows"]] == ["BUX"]
        assert data["rows"][0][2] == "850.00"
        assert "Faqat ruxsat etilgan filiallar: BUX." in data["notes"]
        r = await analyst.post("/api/v1/analytics/queries", headers=csrf(analyst),
                               json=by_branch({"branch_codes": ["TOS", "BUX"]}))
        assert r.status_code == 403 and r.json()["code"] == "BRANCH_FORBIDDEN"
        assert "TOS" in r.json()["message"]
        # Owner cheklanmagan.
        r = await owner.post("/api/v1/analytics/queries", json=by_branch(), headers=csrf(owner))
        all_branches_query = r.json()["data"]["query_spec_id"]
        assert sorted(row[0] for row in r.json()["data"]["rows"]) == ["BUX", "NAM", "TOS"]

        # AI Tool API: doira topshiriq egasining a’zoligidan olinadi.
        cap = capability(tenant, analyst_id)
        q = (await call(client, "run_metric_query", tool_query(), cap, "s1")).json()
        assert q["status"] == "ok" and [row[0] for row in q["data"]["rows"]] == ["BUX"]
        assert "Faqat ruxsat etilgan filiallar: BUX." in q["warnings"]
        denied = (await call(client, "run_metric_query", tool_query(["NAM"]), cap, "s2")).json()
        assert denied["status"] == "error" and denied["error_code"] == "BRANCH_FORBIDDEN"
        # Boshqa foydalanuvchining umumiy so‘rovi asosida taqqoslash ham doirada qoladi.
        cmp = (await call(client, "compare_periods", {
            "query_spec_id": all_branches_query,
            "comparison_range": {"from": "2025-01-01", "to": "2025-04-30"}}, cap, "s3")).json()
        assert cmp["status"] == "ok" and [row[0] for row in cmp["data"]["rows"]] == ["BUX"]
        ex = (await call(client, "explain_contributions", {
            "query_spec_id": all_branches_query, "metric_id": "net_sales", "dimension": "branch",
            "comparison_range": {"from": "2025-01-01", "to": "2025-04-30"}}, cap, "s4")).json()
        assert ex["status"] == "ok"
        assert [c["member"].split(" ")[0] for c in ex["data"]["contributions"]] == ["BUX"]

        # Dashboard: ruxsatsiz filial widget’i ko‘rinmaydi, eksport qilinmaydi.
        wide = await create_dashboard(app_engine, tenant, owner_id, all_branches_query)
        detail = (await analyst.get(f"/api/v1/dashboards/{wide}")).json()
        assert detail["widgets"][0]["status"] == "restricted"
        assert detail["widgets"][0]["data"] is None
        cards = {c["id"]: c for c in (await analyst.get("/api/v1/dashboards")).json()}
        assert cards[wide]["status"] == "restricted" and cards[wide]["kpi"] is None
        r = await analyst.get(f"/api/v1/dashboards/{wide}/widgets/w1/export.csv")
        assert r.status_code == 403
        assert (await owner.get(f"/api/v1/dashboards/{wide}")).json()[
            "widgets"][0]["status"] == "ready"
        # Analyst yaratgan (doiradagi) so‘rov asosidagi dashboard to‘liq ko‘rinadi.
        own = await create_dashboard(app_engine, tenant, owner_id, data["query_spec_id"])
        assert (await analyst.get(f"/api/v1/dashboards/{own}")).json()[
            "widgets"][0]["status"] == "ready"
        # Agent ruxsatsiz natijadan dashboard yarata olmaydi.
        made = (await call(client, "create_dashboard", {
            "title": "Hammasi", "description": None,
            "widgets": [{"title": "x", "type": "table", "query_spec_id": all_branches_query,
                         "text": None}]}, cap, "s5")).json()
        assert made["status"] == "error" and made["error_code"] == "FORBIDDEN"

        # Admin’ga ko‘tarilsa doira olib tashlanadi; doira bekor qilinsa hammasi ko‘rinadi.
        r = await owner.put(url, json={"branch_codes": None}, headers=csrf(owner))
        assert r.status_code == 200 and r.json()["branch_scope"] is None
        r = await analyst.post("/api/v1/analytics/queries", json=by_branch(), headers=csrf(analyst))
        assert len(r.json()["data"]["rows"]) == 3
        await owner.put(url, json={"branch_codes": ["TOS"]}, headers=csrf(owner))
        r = await owner.patch(f"/api/v1/members/{analyst_id}", json={"role": "admin"},
                              headers=csrf(owner))
        assert r.status_code == 200 and r.json()["branch_scope"] is None
