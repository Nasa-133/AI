"""Hujjatlar API (TZ 9, 15): yuklash, qidiruv, bo‘limlar, draft, diff, promote, o‘chirish."""

import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from business.contexts.documents.adapters.files import S3FileStore
from business.contexts.documents.application.common import Viewer, version_of, visible_document
from business.contexts.documents.application.ingest import MAX_DOCUMENT_BYTES
from business.contexts.documents.domain.patch import ReplaceText
from business.contexts.identity.domain.errors import Forbidden
from business.contexts.identity.public import AuthContext
from business.platform.db import tenant_transaction
from business.platform.storage import ObjectTooLarge

from ..wiring import document_services
from .deps import AuthCtx, ContainerDep

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def viewer(ctx: AuthContext) -> Viewer:
    return Viewer(ctx.user_id, ctx.role.value)


class Operation(BaseModel):
    op: Literal["replace_text"] = "replace_text"
    section_id: str = Field(min_length=1, max_length=50)
    find: str = Field(min_length=1, max_length=1000)
    replace: str = Field(max_length=1000)
    occurrence: int = Field(default=1, ge=1, le=50)


class DraftIn(BaseModel):
    base_version_id: UUID
    expected_version_id: UUID
    operations: list[Operation] = Field(min_length=1, max_length=50)
    comment: str | None = Field(default=None, max_length=500)


class PromoteIn(BaseModel):
    version_id: UUID
    expected_current_version_id: UUID


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    document_ids: list[UUID] | None = Field(default=None, max_length=50)


class ShareIn(BaseModel):
    visibility: Literal["private", "tenant"]
    user_ids: list[UUID] = Field(default_factory=list, max_length=200)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload(ctx: AuthCtx, container: ContainerDep,
                 file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    if ctx.role.value == "viewer":
        raise Forbidden("Viewer hujjat yuklay olmaydi.")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload"
        size = 0
        with path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DOCUMENT_BYTES:
                    # Indamay kesilmaydi: foydalanuvchiga limit aytiladi (TZ 9.1).
                    raise ObjectTooLarge("Hujjat 25 MB limitdan oshdi. Faylni bo‘lib yuklang.")
                out.write(chunk)
        async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                      user_id=ctx.user_id) as conn:
            return await document_services(container, conn, ctx.tenant_id).ingest.upload(
                ctx.user_id, file.filename or "hujjat.txt", path)


@router.get("")
async def list_documents(
    ctx: AuthCtx, container: ContainerDep,
    q: str | None = Query(default=None, max_length=200),
) -> list[dict[str, Any]]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await document_services(container, conn, ctx.tenant_id).reading.list_documents(
            viewer(ctx), q)


@router.post("/search")
async def search(body: SearchIn, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await document_services(container, conn, ctx.tenant_id).reading.search(
            viewer(ctx), body.query, body.document_ids)


@router.get("/{document_id}")
async def detail(document_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await document_services(container, conn, ctx.tenant_id).reading.detail(
            viewer(ctx), document_id)


@router.get("/{document_id}/versions/{version_id}/sections")
async def sections(document_id: UUID, version_id: UUID, ctx: AuthCtx,
                   container: ContainerDep) -> list[dict[str, Any]]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await document_services(container, conn, ctx.tenant_id).reading.sections(
            viewer(ctx), document_id, version_id)


@router.get("/{document_id}/versions/{version_id}/download")
async def download(document_id: UUID, version_id: UUID, ctx: AuthCtx,
                   container: ContainerDep) -> Response:
    """ACL tekshiruvidan keyin fayl API orqali beriladi (bucket private, TZ 18)."""
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        services = document_services(container, conn, ctx.tenant_id)
        doc = await visible_document(services.store, viewer(ctx), document_id)
        version = await version_of(services.store, doc, version_id)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "file"
        await S3FileStore(container.storage, container.settings.uploads_bucket).download(
            version.object_ref(), path)
        content = path.read_bytes()
    return Response(content=content, media_type=version.content_type, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(version.filename)}",
        "Cache-Control": "no-store"})


@router.post("/{document_id}/drafts", status_code=status.HTTP_201_CREATED)
async def create_draft(document_id: UUID, body: DraftIn, ctx: AuthCtx,
                       container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await document_services(container, conn, ctx.tenant_id).editing.create_draft(
            viewer(ctx), document_id, body.base_version_id, body.expected_version_id,
            [ReplaceText(o.section_id, o.find, o.replace, o.occurrence) for o in body.operations],
            body.comment)


@router.get("/{document_id}/diff")
async def diff(document_id: UUID, left: UUID, right: UUID, ctx: AuthCtx,
               container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await document_services(container, conn, ctx.tenant_id).reading.compare(
            viewer(ctx), document_id, left, right)


@router.post("/{document_id}/promote")
async def promote(document_id: UUID, body: PromoteIn, ctx: AuthCtx,
                  container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await document_services(container, conn, ctx.tenant_id).editing.promote(
            viewer(ctx), document_id, body.version_id, body.expected_current_version_id)


@router.delete("/{document_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete(document_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await document_services(container, conn, ctx.tenant_id).editing.delete(
            viewer(ctx), document_id)


@router.put("/{document_id}/access")
async def share(document_id: UUID, body: ShareIn, ctx: AuthCtx,
                container: ContainerDep) -> dict[str, Any]:
    for user_id in body.user_ids:
        if await container.identity.role_of(ctx.tenant_id, user_id) is None:
            raise Forbidden("Faqat korxona a’zolariga ulashish mumkin.")
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        services = document_services(container, conn, ctx.tenant_id)
        await services.editing.share(viewer(ctx), document_id, body.visibility, body.user_ids)
        return await services.reading.detail(viewer(ctx), document_id)
