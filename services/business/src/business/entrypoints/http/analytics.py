"""Dashboard doskasi/tafsiloti va metrika sozlamalarini tasdiqlash (TZ 7.1, 8, 15)."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel

from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.contexts.analytics.domain.metrics import CATALOG
from business.contexts.analytics.ports.store import MetricSettings
from business.contexts.dashboards.adapters.sql import AnalyticsQueryResults, SqlDashboardStore
from business.contexts.dashboards.application.service import DashboardService
from business.contexts.identity.domain.errors import Forbidden
from business.contexts.identity.public import Role
from business.platform.db import tenant_transaction

from .deps import AuthCtx, ContainerDep

router = APIRouter(prefix="/api/v1", tags=["analytics"])


class MetricSettingsIn(BaseModel):
    vat_policy: Literal["exclude"] = "exclude"
    returns_policy: Literal["subtract"] = "subtract"
    discount_policy: Literal["respect_source_flag"] = "respect_source_flag"
    counted_statuses: list[Literal["confirmed"]] = ["confirmed"]


@router.get("/metrics")
async def metrics(ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        settings = await SqlAnalyticsStore(conn, ctx.tenant_id).metric_settings()
    return {
        "settings": None if settings is None else {
            "version": settings.version, "settings": settings.settings,
            "approved_at": settings.approved_at.isoformat()},
        "metrics": [{"id": m.id, "name": m.name, "description": m.description,
                     "unit": m.unit.value, "version": m.version} for m in CATALOG.values()],
    }


@router.post("/metric-settings/approve")
async def approve_metric_settings(body: MetricSettingsIn, ctx: AuthCtx,
                                  container: ContainerDep) -> dict[str, Any]:
    """Hisob siyosatini Owner (yoki Admin) tasdiqlaydi; tasdiqsiz moliyaviy query yo‘q."""
    if ctx.role not in (Role.OWNER, Role.ADMIN):
        raise Forbidden("Metrika sozlamalarini faqat Owner yoki Admin tasdiqlaydi.")
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        store = SqlAnalyticsStore(conn, ctx.tenant_id)
        current = await store.metric_settings()
        settings = MetricSettings((current.version if current else 0) + 1, body.model_dump(),
                                  ctx.user_id, datetime.now(UTC))
        await store.save_metric_settings(settings)
    return {"version": settings.version, "settings": settings.settings}


@router.get("/dashboards")
async def dashboards(ctx: AuthCtx, container: ContainerDep,
                     q: str | None = Query(default=None, max_length=200),
                     limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        service = DashboardService(SqlDashboardStore(conn, ctx.tenant_id),
                                   AnalyticsQueryResults(SqlAnalyticsStore(conn, ctx.tenant_id)))
        return await service.cards(limit=limit, query=q)


@router.get("/dashboards/{dashboard_id}")
async def dashboard(dashboard_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        service = DashboardService(SqlDashboardStore(conn, ctx.tenant_id),
                                   AnalyticsQueryResults(SqlAnalyticsStore(conn, ctx.tenant_id)))
        return await service.detail(dashboard_id)
