"""Kontekst servislarini yig‘ish (HTTP va consumer’lar uchun umumiy composition)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from business.bootstrap.container import Container
from business.contexts.documents.adapters.draft_writer import FileDraftWriter
from business.contexts.documents.adapters.files import HttpQueryEmbedder, S3FileStore
from business.contexts.documents.adapters.parser import IsolatedParser
from business.contexts.documents.adapters.sql_store import SqlDocumentStore
from business.contexts.documents.application.editing import DocumentEditing
from business.contexts.documents.application.ingest import DocumentIngest
from business.contexts.documents.application.reading import DocumentReading
from business.contexts.governance.public import (
    POLICY_VERSION,
    BudgetLimits,
    BudgetService,
    SqlBudgetStore,
    SqlPiiVault,
    SqlPrivacySettings,
    TaskPrivacy,
    redact_text,
)
from business.contexts.workspace.adapters.sql import SqlWorkspaceStore
from business.contexts.workspace.application.dispatch import Dispatcher
from business.contexts.workspace.ports.store import BudgetDecision
from business.platform.capability import Capability
from business.platform.outbox import BoundOutbox


@dataclass(frozen=True, slots=True)
class DocumentServices:
    reading: DocumentReading
    ingest: DocumentIngest
    editing: DocumentEditing
    store: SqlDocumentStore


def document_services(container: Container, conn: AsyncConnection,
                      tenant_id: UUID) -> DocumentServices:
    store = SqlDocumentStore(conn, tenant_id)
    files = S3FileStore(container.storage, container.settings.uploads_bucket)
    outbox = BoundOutbox(conn, tenant_id)
    # TZ 13.12: AI’ga (embedding) ketadigan matndan shaxsiy ma’lumot yashiriladi.
    ingest = DocumentIngest(store, files, outbox, IsolatedParser(), tenant_id,
                            redact=redact_text)
    embedder = HttpQueryEmbedder(container.settings.ai_runtime_url,
                                 container.settings.tools_service_token, redact=redact_text)
    return DocumentServices(DocumentReading(store, embedder), ingest,
                            DocumentEditing(store, files, outbox, FileDraftWriter(), ingest,
                                            tenant_id), store)


class CapabilityIssuer:
    def __init__(self, container: Container) -> None:
        self._signer = container.capabilities

    def issue_for_task(self, *, task_id: UUID, tenant_id: UUID, user_id: UUID, role_key: str,
                       tools: tuple[str, ...], expires_at: datetime) -> str:
        return self._signer.issue(Capability(task_id, tenant_id, user_id, role_key, tools,
                                             expires_at))


async def budget_service(container: Container, conn: AsyncConnection,
                         tenant_id: UUID) -> BudgetService:
    s = container.settings
    profile = await container.identity.tenant_profile(tenant_id)
    return BudgetService(SqlBudgetStore(conn, tenant_id),
                         defaults=BudgetLimits(s.budget_daily_limit, s.budget_monthly_limit),
                         reservation=s.budget_task_reservation, timezone=profile.timezone)


class BudgetGateAdapter:
    """Workspace BudgetGate porti → Governance BudgetService (vaqt mintaqasi kerak bo‘lganda)."""

    def __init__(self, container: Container, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._args = (container, conn, tenant_id)
        self._service: BudgetService | None = None

    async def _get(self) -> BudgetService:
        if self._service is None:
            self._service = await budget_service(*self._args)
        return self._service

    async def reserve(self, task_id: UUID) -> BudgetDecision:
        r = await (await self._get()).reserve(task_id)
        return BudgetDecision(r.allowed, r.reservation_id, r.message)

    async def settle(self, task_id: UUID, usage: dict[str, Any]) -> None:
        await (await self._get()).settle(task_id, usage, str(usage.get("currency", "USD")))

    async def release(self, task_id: UUID) -> None:
        await (await self._get()).release(task_id)


async def task_privacy(container: Container, conn: AsyncConnection, tenant_id: UUID,
                       task_id: UUID) -> TaskPrivacy:
    enabled, people = await SqlPrivacySettings(conn, tenant_id).get()
    vault = SqlPiiVault(conn, tenant_id, task_id, container.settings.data_encryption_key)
    return TaskPrivacy(vault, enabled=enabled, mask_people=people)


class PrivacyGateAdapter:
    """Workspace PrivacyGate porti → Governance psevdonimlash (vazifa bo‘yicha token ombori)."""

    def __init__(self, container: Container, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._args = (container, conn, tenant_id)

    async def mask_instruction(self, task_id: UUID, text: str) -> str:
        return await (await task_privacy(*self._args, task_id)).mask_text(text)

    async def unmask_answer(self, task_id: UUID, text: str) -> str:
        return await (await task_privacy(*self._args, task_id)).unmask_text(text)


def task_dispatcher(container: Container, conn: AsyncConnection, tenant_id: UUID) -> Dispatcher:
    return Dispatcher(SqlWorkspaceStore(conn, tenant_id), BoundOutbox(conn, tenant_id),
                      CapabilityIssuer(container), tenant_id=tenant_id,
                      limit=container.settings.agent_parallel_limit,
                      policy_version=POLICY_VERSION, clock=lambda: datetime.now(UTC),
                      budget=BudgetGateAdapter(container, conn, tenant_id),
                      privacy=PrivacyGateAdapter(container, conn, tenant_id))
