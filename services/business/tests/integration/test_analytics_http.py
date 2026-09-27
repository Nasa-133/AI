"""Foydalanuvchi so‘rovi (drill-down) va metrika sozlamalari HTTP orqali."""

from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.platform.db import tenant_transaction

from .test_analytics import load_golden
from .test_identity_http import complete_mfa, csrf, new_client, onboard

pytestmark = pytest.mark.integration


async def test_drilldown_query_and_settings(client: httpx.AsyncClient,
                                            app_engine: AsyncEngine) -> None:
    async with new_client(client) as c:
        _, body = await onboard(c, "Drill MChJ")
        await complete_mfa(c)
        tenant = UUID(body["tenant_id"])
        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=None) as conn:
            await load_golden(SqlAnalyticsStore(conn, tenant), uuid4())

        query = {"metric_ids": ["net_sales"], "date_range": {"from": "2026-01-01", "to": "2026-01-31"},
                 "dimensions": ["product"], "filters": {"branch_codes": ["TOS"]}}
        r = await c.post("/api/v1/analytics/queries", json=query, headers=csrf(c))
        assert r.status_code == 200, r.text
        rows = {row[0]: row[2] for row in r.json()["data"]["rows"]}  # product, name, net_sales
        assert rows == {"P001": "470.00", "P002": "380.00"}  # 600−30−100 va 400−20

        bad = await c.post("/api/v1/analytics/queries", headers=csrf(c),
                           json={**query, "metric_ids": ["net_profit"]})
        assert bad.status_code == 422 and bad.json()["code"] == "UNKNOWN_METRIC"

        approved = await c.post("/api/v1/metric-settings/approve", json={}, headers=csrf(c))
        assert approved.status_code == 200 and approved.json()["version"] == 2
        assert (await c.get("/api/v1/metrics")).json()["settings"]["version"] == 2
