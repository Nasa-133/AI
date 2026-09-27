"""Yuklash va data source API (TZ 9.1, 15). Integratsiyani faqat Owner/Admin boshqaradi."""

from typing import IO, Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from business.bootstrap.container import Container
from business.contexts.identity.domain.errors import Forbidden
from business.contexts.identity.public import AuthContext, Role
from business.contexts.integrations.adapters.sql import SqlIntegrationsStore
from business.contexts.integrations.application.sources import SourceService
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
    connector_id: Literal["file_import", "demo_erp"]
    name: str = Field(default="", max_length=200)
    upload_id: UUID | None = None


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
                    "finance.receivable"]
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
                                                           body.name, body.upload_id)


@router.get("/integrations")
async def list_sources(ctx: AuthCtx, container: ContainerDep) -> list[dict[str, Any]]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return [_json(r) for r in await SqlIntegrationsStore(conn, ctx.tenant_id).list_sources()]


@router.get("/integrations/{source_id}")
async def get_source(source_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return _json(await _service(container, conn, ctx).detail(source_id))


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


@router.post("/integrations/{source_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync(source_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    _require_manager(ctx)
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await _service(container, conn, ctx).sync(ctx.user_id, source_id)
