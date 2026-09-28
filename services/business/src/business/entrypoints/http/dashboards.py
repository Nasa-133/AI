"""Dashboard API (TZ 8.2, 15): doska, tafsilot, tahrir/versiya, ulashish, yangilash, CSV eksport."""

import csv
import io
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from business.bootstrap.container import Container
from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.contexts.analytics.public import StoredQueryRefresher
from business.contexts.dashboards.adapters.sql import AnalyticsQueryResults, SqlDashboardStore
from business.contexts.dashboards.application.service import DashboardService, Viewer
from business.contexts.identity.domain.errors import Forbidden
from business.contexts.identity.public import AuthContext
from business.platform.db import tenant_transaction

from .deps import AuthCtx, ContainerDep

router = APIRouter(prefix="/api/v1/dashboards", tags=["dashboards"])


def _service(conn: AsyncConnection, ctx: AuthContext,
             refresher: StoredQueryRefresher | None = None) -> DashboardService:
    return DashboardService(SqlDashboardStore(conn, ctx.tenant_id),
                            AnalyticsQueryResults(SqlAnalyticsStore(conn, ctx.tenant_id)),
                            refresher)


async def _viewer(ctx: AuthContext, container: Container) -> Viewer:
    return Viewer(ctx.user_id, ctx.role.value,
                  await container.identity.branch_scope_of(ctx.tenant_id, ctx.user_id))


class WidgetEdit(BaseModel):
    id: str = Field(max_length=20)
    title: str | None = Field(default=None, max_length=200)
    type: Literal["kpi", "line", "area", "bar", "stacked_bar", "pie", "funnel", "heatmap",
                  "table", "text"] | None = None


class DashboardEdit(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    widgets: list[WidgetEdit] | None = Field(default=None, min_length=1, max_length=12)


class ShareIn(BaseModel):
    visibility: Literal["private", "tenant"]
    user_ids: list[UUID] = Field(default_factory=list, max_length=200)


@router.get("")
async def cards(ctx: AuthCtx, container: ContainerDep,
                q: str | None = Query(default=None, max_length=200),
                limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    viewer = await _viewer(ctx, container)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await _service(conn, ctx).cards(viewer, limit=limit, query=q)


@router.get("/{dashboard_id}")
async def detail(dashboard_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    viewer = await _viewer(ctx, container)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await _service(conn, ctx).detail(viewer, dashboard_id)


@router.patch("/{dashboard_id}")
async def edit(dashboard_id: UUID, body: DashboardEdit, ctx: AuthCtx,
               container: ContainerDep) -> dict[str, Any]:
    """Nom, tavsif, widget tartibi/turi/o‘chirish — har o‘zgarish yangi versiya."""
    viewer = await _viewer(ctx, container)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        service = _service(conn, ctx)
        await service.edit(viewer, dashboard_id, title=body.title,
                           description=body.description,
                           widgets=[w.model_dump() for w in body.widgets] if body.widgets
                           else None)
        return await service.detail(viewer, dashboard_id)


@router.get("/{dashboard_id}/versions")
async def versions(dashboard_id: UUID, ctx: AuthCtx,
                   container: ContainerDep) -> list[dict[str, Any]]:
    viewer = await _viewer(ctx, container)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await _service(conn, ctx).versions(viewer, dashboard_id)


@router.put("/{dashboard_id}/access")
async def share(dashboard_id: UUID, body: ShareIn, ctx: AuthCtx,
                container: ContainerDep) -> dict[str, Any]:
    """Ruxsat bilan ulashish (TZ 8.2): faqat korxona a’zolariga."""
    for user_id in body.user_ids:
        if await container.identity.role_of(ctx.tenant_id, user_id) is None:
            raise Forbidden("Faqat korxona a’zolariga ulashish mumkin.")
    viewer = await _viewer(ctx, container)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        service = _service(conn, ctx)
        await service.share(viewer, dashboard_id, body.visibility, body.user_ids)
        return await service.detail(viewer, dashboard_id)


@router.post("/{dashboard_id}/refresh")
async def refresh(dashboard_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    """Ruxsat bilan yangilash: oxirgi snapshot bo‘yicha qayta hisob (LLM ishtirokisiz)."""
    profile = await container.identity.tenant_profile(ctx.tenant_id)
    today = datetime.now(UTC).astimezone(ZoneInfo(profile.timezone)).date()
    viewer = await _viewer(ctx, container)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        refresher = StoredQueryRefresher(conn, ctx.tenant_id, user_id=ctx.user_id, today=today,
                                         timezone=profile.timezone,
                                         branch_scope=viewer.branch_scope)
        return await _service(conn, ctx, refresher).refresh(viewer, dashboard_id)


@router.get("/{dashboard_id}/widgets/{widget_id}/export.csv")
async def export_csv(dashboard_id: UUID, widget_id: str, ctx: AuthCtx,
                     container: ContainerDep) -> Response:
    viewer = await _viewer(ctx, container)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        name, rows = await _service(conn, ctx).export_csv(viewer, dashboard_id, widget_id)
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    # UTF-8 BOM — Excel o‘zbekcha harflarni to‘g‘ri ochishi uchun.
    return Response(content="﻿" + buffer.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
                             "Cache-Control": "no-store"})
