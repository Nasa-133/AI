"""Kontekst servislarini yig‘ish (HTTP va consumer’lar uchun umumiy composition)."""

from dataclasses import dataclass
from datetime import UTC, datetime
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
from business.contexts.governance.public import POLICY_VERSION
from business.contexts.workspace.adapters.sql import SqlWorkspaceStore
from business.contexts.workspace.application.dispatch import Dispatcher
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
    ingest = DocumentIngest(store, files, outbox, IsolatedParser(), tenant_id)
    embedder = HttpQueryEmbedder(container.settings.ai_runtime_url,
                                 container.settings.tools_service_token)
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


def task_dispatcher(container: Container, conn: AsyncConnection, tenant_id: UUID) -> Dispatcher:
    return Dispatcher(SqlWorkspaceStore(conn, tenant_id), BoundOutbox(conn, tenant_id),
                      CapabilityIssuer(container), tenant_id=tenant_id,
                      limit=container.settings.agent_parallel_limit,
                      policy_version=POLICY_VERSION, clock=lambda: datetime.now(UTC))
