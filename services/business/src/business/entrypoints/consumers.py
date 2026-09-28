"""Broker consumer’lari (docs/design/stage1.md §3). Har handler inbox bilan bitta tranzaksiyada."""

from typing import Any
from uuid import UUID

from abo_messaging import Envelope, PermanentError
from sqlalchemy.ext.asyncio import AsyncConnection

from business.bootstrap.container import Container
from business.contexts.analytics.adapters.canonical import (
    ContractViolation,
    S3CanonicalBatchReader,
)
from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.contexts.analytics.application.ingest import (
    BatchReady,
    IncrementalNotSupported,
    ingest_batch,
)
from business.contexts.analytics.public import query_reader
from business.contexts.integrations.adapters.sql import SqlIntegrationsStore
from business.contexts.integrations.application.events import IntegrationEvents
from business.contexts.workspace.adapters.sql import SqlWorkspaceStore
from business.contexts.workspace.application.agent_events import AgentEventHandler
from business.platform.db import bind_request_context
from business.platform.outbox import BoundOutbox
from business.platform.storage import ChecksumMismatch

from .wiring import DocumentServices, document_services

ANALYTICS_QUEUE = "business.analytics"
DOCUMENTS_QUEUE = "business.documents"
WORKSPACE_QUEUE = "business.workspace"


class _QueryRefs:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._reader = query_reader(conn, tenant_id)

    async def exists(self, query_id: UUID) -> bool:
        return await self._reader.get_query(query_id) is not None


class Consumers:
    def __init__(self, container: Container) -> None:
        self._c = container

    async def bind(self, conn: AsyncConnection, env: Envelope) -> None:
        # Envelope’dagi tenant vakolat dalili emas — faqat ichki trusted runtime xabarlari uchun
        # ma’lumot doirasini tanlaydi (TZ 13.8).
        await bind_request_context(conn, tenant_id=env.tenant_id, user_id=None)

    async def source_batch_ready(self, conn: AsyncConnection, env: Envelope) -> None:
        profile = await self._c.identity.tenant_profile(env.tenant_id)
        outbox = BoundOutbox(conn, env.tenant_id, correlation_id=env.correlation_id,
                             causation_id=env.event_id, traceparent=env.traceparent)
        try:
            await ingest_batch(SqlAnalyticsStore(conn, env.tenant_id),
                               S3CanonicalBatchReader(self._c.storage), outbox,
                               BatchReady.from_payload(env.payload), timezone=profile.timezone)
        except (ContractViolation, ChecksumMismatch, IncrementalNotSupported) as exc:
            raise PermanentError(str(exc)) from exc

    async def agent_progressed(self, conn: AsyncConnection, env: Envelope) -> None:
        await self._agents(conn, env.tenant_id).progressed(env.payload)

    async def agent_completed(self, conn: AsyncConnection, env: Envelope) -> None:
        await self._agents(conn, env.tenant_id).completed(env.payload)

    def _agents(self, conn: AsyncConnection, tenant_id: UUID) -> AgentEventHandler:
        return AgentEventHandler(SqlWorkspaceStore(conn, tenant_id), _QueryRefs(conn, tenant_id))

    def _integrations(self, conn: AsyncConnection, tenant_id: UUID) -> IntegrationEvents:
        return IntegrationEvents(SqlIntegrationsStore(conn, tenant_id))

    async def schema_discovered(self, conn: AsyncConnection, env: Envelope) -> None:
        await self._integrations(conn, env.tenant_id).schema_discovered(env.payload)

    async def source_configured(self, conn: AsyncConnection, env: Envelope) -> None:
        await self._integrations(conn, env.tenant_id).source_configured(env.payload)

    async def sync_completed(self, conn: AsyncConnection, env: Envelope) -> None:
        await self._integrations(conn, env.tenant_id).sync_completed(env.payload)

    async def sync_failed(self, conn: AsyncConnection, env: Envelope) -> None:
        await self._integrations(conn, env.tenant_id).sync_failed(env.payload)

    def analytics_routes(self) -> dict[str, Any]:
        return {"SourceBatchReady.v1": self.source_batch_ready,
                "SchemaDiscovered.v1": self.schema_discovered,
                "SourceConfigured.v1": self.source_configured,
                "SyncRunCompleted.v1": self.sync_completed,
                "SyncRunFailed.v1": self.sync_failed}

    # --- Hujjatlar (TZ 9) ---
    def _documents(self, conn: AsyncConnection, env: Envelope) -> DocumentServices:
        return document_services(self._c, conn, env.tenant_id)

    async def process_document(self, conn: AsyncConnection, env: Envelope) -> None:
        await self._documents(conn, env).ingest.process(UUID(env.payload["document_id"]),
                                                        UUID(env.payload["version_id"]))

    async def embeddings_generated(self, conn: AsyncConnection, env: Envelope) -> None:
        await self._documents(conn, env).ingest.embeddings_ready(env.payload)

    async def cleanup_document(self, conn: AsyncConnection, env: Envelope) -> None:
        services = self._documents(conn, env)
        document_id = UUID(env.payload["document_id"])
        keys = [(v.bucket, v.object_key) for v in await services.store.versions(document_id)]
        keys += [(self._c.settings.uploads_bucket, f"embeddings-in/{env.tenant_id}/{v_id}.jsonl")
                 for v_id in [v.id for v in await services.store.versions(document_id)]]
        await services.ingest.cleanup(document_id, UUID(env.payload["cleanup_job_id"]), keys)

    def documents_routes(self) -> dict[str, Any]:
        return {"ProcessDocument.v1": self.process_document,
                "EmbeddingsGenerated.v1": self.embeddings_generated,
                "CleanupDocument.v1": self.cleanup_document}

    def workspace_routes(self) -> dict[str, Any]:
        return {"AgentRunProgressed.v1": self.agent_progressed,
                "AgentRunCompleted.v1": self.agent_completed}
