"""Chat, vazifalar va SSE (TZ 15). Uzoq ish HTTP ichida bajarilmaydi: 202 {task_id}."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from business.bootstrap.container import Container
from business.contexts.documents.application.common import Viewer
from business.contexts.governance.public import tools_for
from business.contexts.identity.public import AuthContext
from business.contexts.workspace.adapters.sql import SqlWorkspaceStore
from business.contexts.workspace.application.office import OfficeView
from business.contexts.workspace.application.tasks import Actor, TaskService
from business.platform.db import tenant_transaction
from business.platform.outbox import BoundOutbox

from ..wiring import document_services, task_dispatcher
from .deps import AuthCtx, ContainerDep

router = APIRouter(prefix="/api/v1", tags=["workspace"])
SSE_POLL_SECONDS = 0.5
SSE_HEARTBEAT_SECONDS = 15.0
SSE_MAX_SECONDS = 15 * 60


def _service(container: Container, conn: AsyncConnection, ctx: AuthContext) -> TaskService:
    return TaskService(SqlWorkspaceStore(conn, ctx.tenant_id), BoundOutbox(conn, ctx.tenant_id),
                       task_dispatcher(container, conn, ctx.tenant_id), tools_for)


def _actor(ctx: AuthContext) -> Actor:
    return Actor(ctx.tenant_id, ctx.user_id, ctx.role.value, ())


class ConversationIn(BaseModel):
    title: str = Field(default="Yangi suhbat", max_length=200)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    agent: str | None = Field(default=None, description="Agent roli (masalan sales_analyst)")
    document_ids: list[UUID] = Field(default_factory=list, max_length=10,
                                     description="Kontekst sifatida tanlangan hujjatlar (chip)")


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(body: ConversationIn, ctx: AuthCtx,
                              container: ContainerDep) -> dict[str, str]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        cid = await _service(container, conn, ctx).start_conversation(_actor(ctx), body.title)
    return {"id": str(cid)}


@router.get("/conversations")
async def list_conversations(ctx: AuthCtx, container: ContainerDep) -> list[dict[str, Any]]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        rows = await SqlWorkspaceStore(conn, ctx.tenant_id).list_conversations(ctx.user_id, 100)
    return [{k: str(v) if k == "id" else v for k, v in r.items()} for r in rows]


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: UUID, ctx: AuthCtx,
                        container: ContainerDep) -> list[dict[str, Any]]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        rows = await SqlWorkspaceStore(conn, ctx.tenant_id).list_messages(conversation_id, 500)
    return [json.loads(json.dumps(r, default=str)) for r in rows]


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_202_ACCEPTED)
async def post_message(conversation_id: UUID, body: MessageIn, ctx: AuthCtx,
                       container: ContainerDep,
                       idempotency_key: str | None = Header(default=None, max_length=200),
                       ) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        documents = []
        if body.document_ids:
            # ACL: faqat foydalanuvchi ko‘ra oladigan hujjat kontekstga qo‘shiladi (aks holda 404).
            reading = document_services(container, conn, ctx.tenant_id).reading
            for document_id in dict.fromkeys(body.document_ids):
                d = await reading.detail(Viewer(ctx.user_id, ctx.role.value), document_id)
                documents.append({"id": d["id"], "version_id": d["current_version_id"],
                                  "title": d["title"]})
        return await _service(container, conn, ctx).post_message(
            _actor(ctx), conversation_id, body.content, agent=body.agent,
            idempotency_key=idempotency_key, now=datetime.now(UTC),
            context_documents=documents)


@router.get("/office")
async def office(ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    """Agentlar holati (TZ 6): backend task/step holatidan hosil qilinadi, soxta progress yo‘q."""
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        view = OfficeView(SqlWorkspaceStore(conn, ctx.tenant_id),
                          limit=container.settings.agent_parallel_limit)
        return await view.snapshot(ctx.user_id, datetime.now(UTC))


@router.get("/tasks")
async def list_tasks(ctx: AuthCtx, container: ContainerDep) -> list[dict[str, Any]]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        view = OfficeView(SqlWorkspaceStore(conn, ctx.tenant_id),
                          limit=container.settings.agent_parallel_limit)
        return await view.my_tasks(ctx.user_id)


@router.get("/tasks/{task_id}")
async def get_task(task_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, Any]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await _service(container, conn, ctx).detail(task_id)


@router.post("/tasks/{task_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_task(task_id: UUID, ctx: AuthCtx, container: ContainerDep) -> dict[str, str]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        await _service(container, conn, ctx).cancel(_actor(ctx), task_id)
    return {"status": "cancel_requested"}


@router.get("/tasks/{task_id}/events")
async def task_events(task_id: UUID, request: Request, ctx: AuthCtx, container: ContainerDep,
                      last_event_id: str | None = Header(default=None)) -> StreamingResponse:
    """SSE: persistent `task_events` jadvalidan; qayta ulanishda Last-Event-ID’dan davom etadi."""
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        await _service(container, conn, ctx).detail(task_id)  # mavjudligi va RLS
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

    async def stream() -> AsyncIterator[bytes]:
        after, idle, elapsed = start, 0.0, 0.0
        yield b"retry: 2000\n\n"
        while elapsed < SSE_MAX_SECONDS and not await request.is_disconnected():
            async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                          user_id=ctx.user_id) as conn:
                events = await SqlWorkspaceStore(conn, ctx.tenant_id).events_after(
                    task_id, after, 100)
            for e in events:
                after = e.id
                data = json.dumps({**e.payload, "created_at": e.created_at.isoformat()},
                                  ensure_ascii=False)
                yield f"id: {e.id}\nevent: {e.event_type}\ndata: {data}\n\n".encode()
                if e.event_type == "task.completed":
                    return
            if not events:
                idle += SSE_POLL_SECONDS
                if idle >= SSE_HEARTBEAT_SECONDS:
                    idle = 0.0
                    yield b": heartbeat\n\n"
            await asyncio.sleep(SSE_POLL_SECONDS)
            elapsed += SSE_POLL_SECONDS

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
