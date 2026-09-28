"""Davriy fon ishlari (Business worker): har tenant o‘z RLS kontekstida, alohida tranzaksiyada.

Bir tenant xatosi boshqalarini to‘xtatmaydi. Bir nechta worker parallel ishlasa ham xavfsiz:
osilgan vazifalar `FOR UPDATE SKIP LOCKED`, tozalash qayta urinishi idempotent.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text

from business.bootstrap.container import Container
from business.contexts.documents.adapters.files import S3FileStore
from business.contexts.documents.adapters.sql_store import SqlDocumentStore
from business.contexts.documents.application.maintenance import DocumentMaintenance
from business.contexts.governance.public import SqlAuditLog, SqlPrivacySettings
from business.contexts.workspace.adapters.sql import SqlWorkspaceStore
from business.contexts.workspace.application.maintenance import WorkspaceMaintenance
from business.platform.db import tenant_transaction
from business.platform.outbox import BoundOutbox

from .wiring import BudgetGateAdapter, task_dispatcher

logger = logging.getLogger("business.jobs")


@dataclass(slots=True)
class MaintenanceStats:
    tenants: int = 0
    reaped: int = 0
    cleanups_retried: int = 0
    drafts_purged: int = 0
    conversations_purged: int = 0
    audit_purged: int = 0
    errors: list[str] = field(default_factory=list)


async def tenant_ids(container: Container) -> list[UUID]:
    async with container.engine.connect() as conn:
        rows = await conn.execute(text("SELECT id FROM platform.tenant_registry ORDER BY id"))
        return [r.id for r in rows]


async def run_for_tenant(container: Container, tenant_id: UUID, stats: MaintenanceStats) -> None:
    s = container.settings
    async with tenant_transaction(container.engine, tenant_id=tenant_id, user_id=None) as conn:
        ws = WorkspaceMaintenance(SqlWorkspaceStore(conn, tenant_id),
                                  task_dispatcher(container, conn, tenant_id),
                                  BudgetGateAdapter(container, conn, tenant_id))
        stats.reaped += await ws.reap_stuck()
        stats.conversations_purged += await ws.apply_retention(s.retention_conversation_days)
        docs = DocumentMaintenance(SqlDocumentStore(conn, tenant_id),
                                   S3FileStore(container.storage, s.uploads_bucket),
                                   BoundOutbox(conn, tenant_id))
        stats.cleanups_retried += await docs.retry_cleanups()
        stats.drafts_purged += await docs.purge_stale_drafts(s.retention_draft_days)
        stats.audit_purged += await SqlAuditLog(conn, tenant_id).purge(s.retention_audit_days)
        # Psevdonim tokenlari faqat vazifa davomida kerak (javob allaqachon tiklangan).
        await SqlPrivacySettings(conn, tenant_id).purge_tokens(days=7)


async def run_maintenance(container: Container) -> MaintenanceStats:
    stats = MaintenanceStats()
    for tenant_id in await tenant_ids(container):
        stats.tenants += 1
        try:
            await run_for_tenant(container, tenant_id, stats)
        except Exception as exc:  # bir tenant xatosi boshqalarini to‘xtatmaydi
            logger.exception("Fon ishi xatosi (tenant=%s)", tenant_id)
            stats.errors.append(f"{tenant_id}: {type(exc).__name__}")
    return stats


async def maintenance_loop(container: Container, stop: asyncio.Event) -> None:
    interval = container.settings.maintenance_interval_seconds
    while not stop.is_set():
        stats = await run_maintenance(container)
        if (stats.reaped or stats.cleanups_retried or stats.drafts_purged
                or stats.conversations_purged or stats.errors):
            logger.info("Fon ishlari: %s", stats)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
