"""Inbox deduplikatsiyasi va xabarni qayta ishlash natijasi (broker’dan mustaqil)."""

import logging
from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from .envelope import Envelope, InvalidEnvelope
from .store import make_tables

logger = logging.getLogger(__name__)

Handler = Callable[[AsyncConnection, Envelope], Awaitable[None]]
TransactionHook = Callable[[AsyncConnection, Envelope], Awaitable[None]]


class PermanentError(Exception):
    """Qayta urinish foyda bermaydigan xato (schema, ruxsat, biznes qoidasi) — DLQ."""


class Outcome(StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    RETRY = "retry"
    DEAD = "dead"


class InboxProcessor:
    """Bitta consumer uchun: dedup + handler + inbox yozuvi bitta tranzaksiyada.

    Handler o‘z DB o‘zgarishlarini (va kerak bo‘lsa yangi outbox xabarlarini) shu
    `conn` orqali yozadi — shunda qayta ishlash va dedup belgisi atomar bo‘ladi.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        consumer: str,
        handlers: Mapping[str, Handler],
        schema: str = "messaging",
        on_transaction_start: TransactionHook | None = None,
    ) -> None:
        self._engine = engine
        self._consumer = consumer
        self._handlers = dict(handlers)
        self._inbox = make_tables(schema)[1]
        self._on_tx_start = on_transaction_start

    @property
    def event_types(self) -> list[str]:
        return sorted(self._handlers)

    async def process(self, body: bytes, *, attempt: int, max_attempts: int) -> Outcome:
        try:
            envelope = Envelope.from_json(body)
        except InvalidEnvelope:
            logger.exception("Envelope noto‘g‘ri, DLQ", extra={"consumer": self._consumer})
            return Outcome.DEAD
        handler = self._handlers.get(envelope.event_type)
        if handler is None:
            # Noma’lum major versiya yoki tur: aniq sabab bilan DLQ (TZ 13.11).
            logger.error("Handler yo‘q: %s", envelope.event_type,
                         extra={"consumer": self._consumer})
            return Outcome.DEAD
        try:
            async with self._engine.connect() as conn, conn.begin():
                if self._on_tx_start is not None:
                    await self._on_tx_start(conn, envelope)
                inserted = await conn.execute(
                    insert(self._inbox)
                    .values(event_id=envelope.event_id, consumer=self._consumer,
                            processed_at=func.now())
                    .on_conflict_do_nothing()
                    .returning(self._inbox.c.event_id)
                )
                if inserted.first() is None:
                    return Outcome.DUPLICATE
                await handler(conn, envelope)
        except PermanentError:
            logger.exception("Doimiy xato, DLQ", extra={"event_id": str(envelope.event_id)})
            return Outcome.DEAD
        except Exception:
            outcome = Outcome.RETRY if attempt < max_attempts else Outcome.DEAD
            logger.exception("Handler xatosi (%s)", outcome,
                             extra={"event_id": str(envelope.event_id), "attempt": attempt})
            return outcome
        return Outcome.PROCESSED
