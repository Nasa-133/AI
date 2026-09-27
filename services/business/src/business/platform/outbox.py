"""Business outbox adapteri: joriy tranzaksiyada envelope yozadi (ADR 004)."""

from typing import Any
from uuid import UUID

from abo_messaging import enqueue, new_envelope
from sqlalchemy.ext.asyncio import AsyncConnection


class BoundOutbox:
    """Kontekstlarning `publish(...)` portlarini qondiradi; tenant va zanjir ID’lari bog‘langan."""

    def __init__(self, conn: AsyncConnection, tenant_id: UUID, *,
                 correlation_id: UUID | None = None, causation_id: UUID | None = None,
                 traceparent: str | None = None) -> None:
        self._conn = conn
        self._tenant = tenant_id
        self._correlation = correlation_id
        self._causation = causation_id
        self._traceparent = traceparent

    async def publish(self, event_type: str, payload: dict[str, Any], *, aggregate_id: UUID,
                      aggregate_version: int) -> None:
        await enqueue(self._conn, new_envelope(
            event_type=event_type, producer="business", tenant_id=self._tenant,
            aggregate_id=aggregate_id, aggregate_version=aggregate_version, payload=payload,
            correlation_id=self._correlation, causation_id=self._causation,
            traceparent=self._traceparent,
        ))
