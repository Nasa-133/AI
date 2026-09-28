"""Dashboard tahriri, versiyalar, ulashish (ACL), yangilash va CSV eksport (TZ 3, 8.2, 9.4)."""

from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.contexts.dashboards.domain.access import csv_safe
from business.platform.db import tenant_transaction
from tests.unit.identity.fakes import RecordingNotifier

from .test_analytics import load_golden
from .test_identity_http import PASSWORD, complete_mfa, csrf, new_client, onboard

pytestmark = pytest.mark.integration


async def monthly_query(c: httpx.AsyncClient) -> str:
    """Foydalanuvchi so‘rovi; dashboard esa shu natijaga bog‘lanadi (create_dashboard mantig‘i)."""
    q = {"metric_ids": ["net_sales"], "date_range": {"from": "2026-01-01", "to": "2026-04-30"},
         "dimensions": ["month"], "filters": {}}
    r = await c.post("/api/v1/analytics/queries", json=q, headers=csrf(c))
    assert r.status_code == 200, r.text
    return str(r.json()["data"]["query_spec_id"])


async def test_edit_versions_share_refresh_export(
    client: httpx.AsyncClient, app_engine: AsyncEngine, notifier: RecordingNotifier
) -> None:
    from business.contexts.dashboards.adapters.sql import AnalyticsQueryResults, SqlDashboardStore
    from business.contexts.dashboards.application.service import DashboardService

    async with new_client(client) as owner, new_client(client) as viewer:
        _, body = await onboard(owner, "Dash MChJ")
        await complete_mfa(owner)
        tenant, owner_id = UUID(body["tenant_id"]), UUID(body["user_id"])
        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=owner_id) as conn:
            await load_golden(SqlAnalyticsStore(conn, tenant), uuid4())
        query_id = await monthly_query(owner)
        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=owner_id) as conn:
            service = DashboardService(SqlDashboardStore(conn, tenant),
                                       AnalyticsQueryResults(SqlAnalyticsStore(conn, tenant)))
            d = await service.create(user_id=owner_id, task_id=None, title="=Savdo",
                                     description=None, widgets=[
                                         {"title": "Oylar", "type": "line",
                                          "query_spec_id": query_id, "text": None}])
        dash = str(d.id)

        # Tahrir → yangi versiya; tur almashtirish tekshiriladi (KPI ko‘p qatorli natijaga mos emas).
        r = await owner.patch(f"/api/v1/dashboards/{dash}", headers=csrf(owner), json={
            "title": "Savdo dinamikasi", "widgets": [{"id": "w1", "type": "bar"}]})
        assert r.status_code == 200 and r.json()["version"] == 2, r.text
        assert r.json()["widgets"][0]["type"] == "bar" and r.json()["can_edit"] is True
        bad = await owner.patch(f"/api/v1/dashboards/{dash}", headers=csrf(owner),
                                json={"widgets": [{"id": "w1", "type": "kpi"}]})
        assert bad.status_code == 422 and bad.json()["code"] == "INVALID_DASHBOARD"
        versions = (await owner.get(f"/api/v1/dashboards/{dash}/versions")).json()
        assert [v["version"] for v in versions] == [2, 1]

        # Viewer: private dashboard ko‘rinmaydi, ulashilgach ko‘rinadi, lekin tahrirlay olmaydi.
        email = f"viewer-{uuid4().hex[:6]}@demo.uz"
        await owner.post("/api/v1/invitations", json={"email": email, "role": "viewer"},
                         headers=csrf(owner))
        token = next(t for e, t in notifier.invitations if e == email)
        r = await viewer.post("/api/v1/invitations/accept", json={"token": token,
                                                                  "password": PASSWORD})
        viewer_id = r.json()["user_id"]
        r = await owner.put(f"/api/v1/dashboards/{dash}/access", headers=csrf(owner),
                            json={"visibility": "private", "user_ids": []})
        assert r.status_code == 200 and r.json()["visibility"] == "private"
        assert (await viewer.get("/api/v1/dashboards")).json() == []
        assert (await viewer.get(f"/api/v1/dashboards/{dash}")).status_code == 404
        assert (await viewer.get(
            f"/api/v1/dashboards/{dash}/widgets/w1/export.csv")).status_code == 404
        await owner.put(f"/api/v1/dashboards/{dash}/access", headers=csrf(owner),
                        json={"visibility": "private", "user_ids": [viewer_id]})
        detail = (await viewer.get(f"/api/v1/dashboards/{dash}")).json()
        assert detail["can_edit"] is False
        r = await viewer.patch(f"/api/v1/dashboards/{dash}", headers=csrf(viewer),
                               json={"title": "X"})
        assert r.status_code == 403
        stranger = await owner.put(f"/api/v1/dashboards/{dash}/access", headers=csrf(owner),
                                   json={"visibility": "private", "user_ids": [str(uuid4())]})
        assert stranger.status_code == 403

        # Yangilash: yangi query ID va versiya; raqamlar o‘sha snapshot’da o‘zgarmaydi.
        r = await owner.post(f"/api/v1/dashboards/{dash}/refresh", headers=csrf(owner))
        assert r.status_code == 200 and r.json() == {"version": 3, "not_refreshed": []}
        after = (await owner.get(f"/api/v1/dashboards/{dash}")).json()
        assert after["widgets"][0]["query_spec_id"] != query_id

        # CSV: BOM, sarlavha, qiymatlar; ACL’dan o‘tgan foydalanuvchi uchun.
        r = await viewer.get(f"/api/v1/dashboards/{dash}/widgets/w1/export.csv")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        lines = r.text.lstrip("﻿").splitlines()
        assert lines[0] == "month,net_sales" and lines[1] == "2026-01,850.00"


def test_csv_formula_injection_is_neutralized() -> None:
    assert csv_safe("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")"
    assert csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert csv_safe("-100.00") == "-100.00"  # oddiy manfiy son o‘zgarmaydi
    assert csv_safe(None) == ""
