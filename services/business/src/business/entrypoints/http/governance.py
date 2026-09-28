"""Boshqaruv: AI budjeti (TZ 19) — holat hamma a’zolarga, limitni faqat egasi o‘zgartiradi."""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from business.platform.db import tenant_transaction

from ..wiring import budget_service
from .deps import AuthCtx, ContainerDep

router = APIRouter(prefix="/api/v1", tags=["governance"])


class BudgetIn(BaseModel):
    daily_limit: Decimal | None = Field(default=None, ge=0, le=1_000_000, decimal_places=2)
    monthly_limit: Decimal | None = Field(default=None, ge=0, le=10_000_000, decimal_places=2)


@router.get("/budget")
async def get_budget(ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await (await budget_service(container, conn, ctx.tenant_id)).overview()


@router.put("/budget")
async def put_budget(body: BudgetIn, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        service = await budget_service(container, conn, ctx.tenant_id)
        return await service.update(ctx.role.value, ctx.user_id, body.daily_limit,
                                    body.monthly_limit)
