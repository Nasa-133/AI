"""Unit of Work va outbox’ga yozuvchi EventSink."""

from types import TracebackType
from typing import Any, Self
from uuid import UUID

from abo_messaging import enqueue, new_envelope
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction

from ..ports.repository import MessageContext
from .sql_repo import SqlIntegrationRepository


async def bind_tenant(conn: AsyncConnection, tenant_id: UUID | None) -> None:
    await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"),
                       {"t": str(tenant_id) if tenant_id else ""})


class OutboxEventSink:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def emit(self, event_type: str, payload: dict[str, Any], *, context: MessageContext,
                   aggregate_id: UUID, aggregate_version: int) -> None:
        await enqueue(self._conn, new_envelope(
            event_type=event_type, producer="integration_runtime", tenant_id=context.tenant_id,
            aggregate_id=aggregate_id, aggregate_version=aggregate_version, payload=payload,
            correlation_id=context.correlation_id, causation_id=context.causation_id,
            traceparent=context.traceparent,
        ))


class ConnectionScope:
    """Consumer tranzaksiyasiga bog‘langan repo + sink (commit’ni InboxProcessor qiladi)."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.repo = SqlIntegrationRepository(conn)
        self.events = OutboxEventSink(conn)


class SqlUnitOfWork:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._conn: AsyncConnection | None = None
        self._tx: AsyncTransaction | None = None
        self._committed = False

    @property
    def repo(self) -> SqlIntegrationRepository:
        assert self._conn is not None
        return SqlIntegrationRepository(self._conn)

    @property
    def events(self) -> OutboxEventSink:
        assert self._conn is not None
        return OutboxEventSink(self._conn)

    async def __aenter__(self) -> Self:
        self._conn = await self._engine.connect()
        self._tx = await self._conn.begin()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None:
        assert self._conn is not None and self._tx is not None
        try:
            if not self._committed and self._tx.is_active:
                await self._tx.rollback()
        finally:
            await self._conn.close()

    async def bind(self, tenant_id: UUID | None) -> None:
        assert self._conn is not None
        await bind_tenant(self._conn, tenant_id)

    async def commit(self) -> None:
        assert self._tx is not None
        await self._tx.commit()
        self._committed = True


class SqlUnitOfWorkFactory:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    def __call__(self) -> SqlUnitOfWork:
        return SqlUnitOfWork(self._engine)
