"""Yuklash va data source API (TZ 9.1, 15). Integratsiyani faqat Owner/Admin boshqaradi."""

from datetime import UTC, datetime, timedelta
from typing import IO, Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from business.bootstrap.container import Container
from business.contexts.analytics.public import SourceDatasets
from business.contexts.identity.domain.errors import Forbidden
from business.contexts.identity.public import AuthContext, Role
from business.contexts.integrations.adapters.sql import SqlIntegrationsStore
from business.contexts.integrations.application.sources import SourceService
from business.contexts.integrations.domain.freshness import freshness
from business.platform.db import tenant_transaction
from business.platform.outbox import BoundOutbox

from .deps import AuthCtx, ContainerDep

router = APIRouter(prefix="/api/v1", tags=["integrations"])


class _Files:
    def __init__(self, container: Container) -> None:
        self._storage, self._bucket = container.storage, container.settings.uploads_bucket

    async def put(self, key: str, source: IO[bytes], *, max_bytes: int,
                  content_type: str) -> dict[str, Any]:
        ref = await self._storage.put_stream(self._bucket, key, source, max_bytes=max_bytes,
                                             content_type=content_type)
        return ref.to_json()


def _require_manager(ctx: AuthContext) -> None:
    if ctx.role not in (Role.OWNER, Role.ADMIN):
        raise Forbidden("Integratsiyalarni faqat Owner yoki Admin boshqaradi.")


def _service(container: Container, conn: AsyncConnection, ctx: AuthContext) -> SourceService:
    return SourceService(SqlIntegrationsStore(conn, ctx.tenant_id), _Files(container),
                         BoundOutbox(conn, ctx.tenant_id), ctx.tenant_id)


def _json(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v.isoformat() if hasattr(v, "isoformat")
                else v) for k, v in row.items()}


class SourceIn(BaseModel):
    connector_id: Literal["file_import", "demo_erp", "erp_api", "crm_api"]
    name: str = Field(default="", max_length=200)
    upload_id: UUID | None = None
    # Ko‘p obyektli manba (ERP): shu manba qaysi obyekt uchun (mapping oynasida oldindan tanlanadi).
    entity: Literal["sales.order_line", "sales.return", "inventory.movement",
                    "finance.receivable", "crm.deal"] | None = None


class MappingItem(BaseModel):
    canonical_field: str = Field(max_length=100)
    source_column: str | None = Field(default=None, max_length=200)
    transform: Literal["text", "decimal", "decimal_or_null", "datetime_tz", "date", "status_map",
                       "const"]
    constant: str | None = Field(default=None, max_length=200)


class StatusMapItem(BaseModel):
    source_value: str = Field(max_length=200)
    canonical_value: str = Field(max_length=50)


class MappingIn(BaseModel):
    entity: Literal["sales.order_line", "sales.return", "inventory.movement",
                    "finance.receivable", "crm.deal"]
    mapping: list[MappingItem] = Field(min_length=1, max_length=100)
    status_map: list[StatusMapItem] = Field(default_factory=list, max_length=100)


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload(ctx: AuthCtx, container: ContainerDep, file: Annotated[UploadFile, File()],
                 purpose: Annotated[Literal["document", "dataset_import"], Form()],
                 ) -> dict[str, Any]:
    _require_manager(ctx)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await _service(container, conn, ctx).upload(
            ctx.user_id, file.filename or "fayl", file.content_type or "application/octet-stream",
            file.file, purpose)


@router.post("/integrations", status_code=status.HTTP_202_ACCEPTED)
async def create_source(body: SourceIn, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    _require_manager(ctx)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await _service(container, conn, ctx).create(ctx.user_id, body.connector_id,
                                                           body.name, body.upload_id, body.entity)


def _usage(source_id: UUID, by_source: dict[UUID, list[dict[str, Any]]],
           names: dict[UUID, str]) -> dict[str, Any] | None:
    """Analitikada hisobga olinadimi: takroriy baza bo‘lsa — qaysi manbaning takrori."""
    rows = by_source.get(source_id)
    if not rows:
        return None
    dup = next((r for r in rows if not r["is_active"]), None)
    if dup is None:
        return {"counted": True, "duplicate_of": None, "duplicate_of_name": None}
    other = dup["duplicate_of_source"]
    return {"counted": False, "duplicate_of": str(other) if other else None,
            "duplicate_of_name": names.get(other) if other else None,
            "overlap": float(dup["overlap"]) if dup["overlap"] is not None else None}


@router.get("/integrations")
async def list_sources(ctx: AuthCtx, container: ContainerDep) -> list[dict[str, Any]]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        rows = await SqlIntegrationsStore(conn, ctx.tenant_id).list_sources()
        by_source = await SourceDatasets(conn, ctx.tenant_id).status()
    names = {r["id"]: r["name"] for r in rows}
    return [{**_json(r), "usage": _usage(r["id"], by_source, names)} for r in rows]


@router.get("/data-freshness")
async def data_freshness(ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    """I03: import/sync kutilayotgani va dashboardlar “eskirgan”ligi (UI belgisi uchun)."""
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        sources = await SqlIntegrationsStore(conn, ctx.tenant_id).list_sources()
    stale_after = timedelta(seconds=container.settings.data_stale_after_seconds)
    return freshness(sources, datetime.now(UTC), stale_after).to_json()


@router.get("/integrations/{source_id}")
async def get_source(source_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        source = await _service(container, conn, ctx).detail(source_id)
        by_source = await SourceDatasets(conn, ctx.tenant_id).status()
        names = {r["id"]: r["name"]
                 for r in await SqlIntegrationsStore(conn, ctx.tenant_id).list_sources()}
    return {**_json(source), "usage": _usage(source_id, by_source, names)}


@router.post("/integrations/{source_id}/mapping", status_code=status.HTTP_202_ACCEPTED)
async def approve_mapping(source_id: UUID, body: MappingIn, ctx: AuthCtx,
                          container: ContainerDep) -> dict[str, Any]:
    """Manba → canonical mapping’ni tasdiqlash (TZ 7.1): yangi versiya Integration’ga ketadi."""
    _require_manager(ctx)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await _service(container, conn, ctx).approve_mapping(
            ctx.user_id, source_id, body.entity, [m.model_dump() for m in body.mapping],
            [s.model_dump() for s in body.status_map])


@router.post("/integrations/{source_id}/use")
async def use_source(source_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    """Takroriy bazalardan qaysi biri hisobga olinishini foydalanuvchi tanlaydi (masalan, eski
    CSV o‘rniga ERP). Tanlangan manba bilan bir xil bo‘lganlar hisobdan chiqadi."""
    _require_manager(ctx)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        await _service(container, conn, ctx).detail(source_id)  # mavjudligi (RLS)
        deactivated = await SourceDatasets(conn, ctx.tenant_id).use(source_id)
    return {"id": str(source_id), "deactivated_datasets": [str(d) for d in deactivated]}


@router.post("/integrations/{source_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync(source_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    _require_manager(ctx)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await _service(container, conn, ctx).sync(ctx.user_id, source_id)
