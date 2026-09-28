"""Audit middleware: muvaffaqiyatli (2xx) o‘zgartiruvchi so‘rovlar jurnalga yoziladi.

Yozuvda faqat identifikatorlar (yo‘l parametrlari) — so‘rov tanasi, hujjat matni va
credential yozilmaydi (TZ 18). Harakatdan keyin alohida tranzaksiyada.
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from business.contexts.governance.public import SqlAuditLog, read_audit
from business.platform.db import tenant_transaction

from .deps import AuthCtx, ContainerDep

logger = logging.getLogger("business.audit")

# (metod, route shabloni) → (harakat, obyekt turi, obyekt ID’si olinadigan yo‘l parametri)
AUDITED: dict[tuple[str, str], tuple[str, str | None, str | None]] = {
    ("POST", "/api/v1/tenants"): ("tenant.created", "tenant", None),
    ("POST", "/api/v1/auth/login"): ("auth.login", None, None),
    ("POST", "/api/v1/auth/logout"): ("auth.logout", None, None),
    ("POST", "/api/v1/auth/mfa/verify"): ("auth.mfa_verified", None, None),
    ("POST", "/api/v1/session/tenant"): ("auth.tenant_switched", None, None),
    ("POST", "/api/v1/invitations"): ("member.invited", None, None),
    ("POST", "/api/v1/invitations/accept"): ("member.joined", None, None),
    ("PATCH", "/api/v1/members/{user_id}"): ("member.role_changed", "user", "user_id"),
    ("DELETE", "/api/v1/members/{user_id}"): ("member.removed", "user", "user_id"),
    ("POST", "/api/v1/metric-settings/approve"): ("metrics.settings_approved", None, None),
    ("PUT", "/api/v1/budget"): ("budget.updated", None, None),
    ("PUT", "/api/v1/privacy"): ("privacy.updated", None, None),
    ("POST", "/api/v1/documents"): ("document.uploaded", None, None),
    ("POST", "/api/v1/documents/{document_id}/drafts"): (
        "document.draft_created", "document", "document_id"),
    ("POST", "/api/v1/documents/{document_id}/promote"): (
        "document.promoted", "document", "document_id"),
    ("DELETE", "/api/v1/documents/{document_id}"): ("document.deleted", "document", "document_id"),
    ("PUT", "/api/v1/documents/{document_id}/access"): (
        "document.shared", "document", "document_id"),
    ("PATCH", "/api/v1/dashboards/{dashboard_id}"): (
        "dashboard.edited", "dashboard", "dashboard_id"),
    ("PUT", "/api/v1/dashboards/{dashboard_id}/access"): (
        "dashboard.shared", "dashboard", "dashboard_id"),
    ("POST", "/api/v1/integrations"): ("integration.created", None, None),
    ("POST", "/api/v1/integrations/{source_id}/mapping"): (
        "integration.mapping_approved", "source", "source_id"),
    ("POST", "/api/v1/integrations/{source_id}/sync"): (
        "integration.sync_started", "source", "source_id"),
    ("POST", "/api/v1/tasks/{task_id}/cancel"): ("task.cancelled", "task", "task_id"),
}


class AuditMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            await self.app(scope, receive, send)
            return
        status: dict[str, int] = {}

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        await self.app(scope, receive, capture)
        if 200 <= status.get("code", 500) < 300:
            try:
                await _record(scope)
            except Exception:  # audit xatosi foydalanuvchi amalini buzmaydi, lekin ko‘rinadi
                logger.exception("Audit yozuvi saqlanmadi")


async def _record(scope: Scope) -> None:
    route = scope.get("route")
    entry = AUDITED.get((scope["method"], getattr(route, "path", "")))
    actor = scope.get("state", {}).get("audit_actor")
    if entry is None or actor is None:
        return
    action, target_type, param = entry
    tenant_id, user_id = actor
    params = scope.get("path_params", {})
    container = scope["app"].state.container
    client = scope.get("client")
    async with tenant_transaction(container.engine, tenant_id=tenant_id,
                                  user_id=user_id) as conn:
        await SqlAuditLog(conn, tenant_id).record(
            actor_id=user_id, actor_kind="user", action=action, target_type=target_type,
            target_id=str(params[param]) if param else None,
            details={k: str(v) for k, v in params.items()}, ip=client[0] if client else None)


def mark_actor(scope_state: Any, tenant_id: UUID, user_id: UUID) -> None:
    """Auth’dan keyin (yoki login/ro‘yxatdan o‘tishda) audit uchun aktorni belgilash."""
    scope_state.audit_actor = (tenant_id, user_id)


router = APIRouter(prefix="/api/v1", tags=["governance"])


@router.get("/audit")
async def audit(ctx: AuthCtx, container: ContainerDep, limit: int = Query(default=50, le=200),
                before: int | None = Query(default=None)) -> list[dict[str, Any]]:
    async with tenant_transaction(container.engine, tenant_id=ctx.tenant_id,
                                  user_id=ctx.user_id) as conn:
        return await read_audit(SqlAuditLog(conn, ctx.tenant_id), ctx.role.value, limit=limit,
                                before_id=before)
