from dataclasses import dataclass
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any, Protocol, Self
from uuid import UUID

from ..domain.batch import RejectionReport
from ..domain.mapping import SourceMapping
from .connector import ObjectRef

TERMINAL_STATUSES = frozenset({"succeeded", "partial", "failed"})


@dataclass(frozen=True, slots=True)
class MessageContext:
    """Kiruvchi command’dan olingan kuzatuv zanjiri; chiquvchi eventlar shunga bog‘lanadi."""

    tenant_id: UUID
    correlation_id: UUID
    causation_id: UUID
    traceparent: str | None


@dataclass(frozen=True, slots=True)
class SyncRun:
    id: UUID
    tenant_id: UUID
    data_source_id: UUID
    connector_id: str
    mode: str
    mapping_version: int
    object_ref: ObjectRef | None
    requested_by: UUID
    status: str
    context: MessageContext


@dataclass(frozen=True, slots=True)
class BatchRecord:
    id: UUID
    tenant_id: UUID
    sync_run_id: UUID
    data_source_id: UUID
    connector_id: str
    connector_version: str
    entity: str
    canonical_schema_version: int
    record_count: int
    object_ref: ObjectRef
    extracted_at: datetime
    is_full_snapshot: bool


@dataclass(frozen=True, slots=True)
class ClaimedRun:
    sync_run_id: UUID
    tenant_id: UUID
    attempts: int


class IntegrationRepository(Protocol):
    async def ensure_data_source(
        self, tenant_id: UUID, data_source_id: UUID, connector_id: str
    ) -> str:
        """Yo‘q bo‘lsa yaratadi; mavjud manbaning connector_id’sini qaytaradi."""
        ...

    async def get_mapping(self, data_source_id: UUID, version: int) -> SourceMapping | None: ...

    async def add_mapping(
        self,
        *,
        tenant_id: UUID,
        data_source_id: UUID,
        version: int,
        mapping: SourceMapping,
        approved_by: UUID,
        approved_at: datetime,
    ) -> None: ...

    async def add_sync_run(self, run: SyncRun) -> bool:
        """Takroriy command (bir xil sync_run_id) uchun False."""
        ...

    async def get_sync_run(self, sync_run_id: UUID) -> SyncRun | None: ...
    async def mark_running(self, sync_run_id: UUID) -> None: ...

    async def finish_sync_run(
        self,
        sync_run_id: UUID,
        *,
        status: str,
        record_count: int,
        rejections: RejectionReport,
        error_code: str | None,
    ) -> None: ...

    async def insert_batch(self, batch: BatchRecord) -> bool:
        """(sync_run_id, entity) allaqachon bo‘lsa False — ikkinchi batch yaratilmaydi."""
        ...

    async def enqueue_run(self, sync_run_id: UUID, tenant_id: UUID) -> None: ...
    async def claim_run(self, owner: str, lease: timedelta) -> ClaimedRun | None: ...
    async def extend_lease(self, sync_run_id: UUID, owner: str, lease: timedelta) -> None: ...
    async def release_run(self, sync_run_id: UUID, delay: timedelta) -> None: ...
    async def complete_run(self, sync_run_id: UUID) -> None: ...


class EventSink(Protocol):
    async def emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        context: MessageContext,
        aggregate_id: UUID,
        aggregate_version: int,
    ) -> None:
        """Joriy lokal tranzaksiya ichida outbox’ga yozadi."""
        ...


class IntegrationUnitOfWork(Protocol):
    @property
    def repo(self) -> IntegrationRepository: ...
    @property
    def events(self) -> EventSink: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def bind(self, tenant_id: UUID | None) -> None: ...
    async def commit(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> IntegrationUnitOfWork: ...
