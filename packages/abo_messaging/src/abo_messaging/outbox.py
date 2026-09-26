"""Transactional outbox (TZ 13.8): domain o‘zgarishi va xabar bitta lokal tranzaksiyada."""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from sqlalchemy import Table, and_, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from .envelope import Envelope
from .store import make_tables

logger = logging.getLogger(__name__)


class Publisher(Protocol):
    async def publish(self, *, routing_key: str, body: bytes, message_id: str) -> None:
        """Broker tasdiqlagandan keyin qaytadi (publisher confirm); aks holda xato."""
        ...


async def enqueue(
    conn: AsyncConnection, envelope: Envelope, *, schema: str = "messaging"
) -> None:
    """Chaqiruvchi tranzaksiyasi ichida outbox yozuvi. Routing key = event_type."""
    outbox, _ = make_tables(schema)
    await conn.execute(
        insert(outbox).values(
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            routing_key=envelope.event_type,
            tenant_id=envelope.tenant_id,
            envelope=json.loads(envelope.to_json()),
            created_at=func.now(),
            attempts=0,
            next_attempt_at=func.now(),
        )
    )


@dataclass(frozen=True, slots=True)
class RelayStats:
    sent: int
    failed_attempts: int
    dead: int


class OutboxRelay:
    """Yuborilmagan yozuvlarni brokerga chiqaradi; tasdiqdan keyingina `sent_at` qo‘yadi.

    Bir nechta relay parallel ishlashi mumkin (`FOR UPDATE SKIP LOCKED`). Relay publish
    va `sent_at` commit orasida yiqilsa xabar qayta yuboriladi — shuning uchun yetkazish
    at-least-once va consumer inbox bilan deduplikatsiya qiladi.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        publisher: Publisher,
        *,
        schema: str = "messaging",
        batch_size: int = 100,
        max_attempts: int = 10,
        base_backoff: timedelta = timedelta(seconds=2),
        max_backoff: timedelta = timedelta(minutes=5),
    ) -> None:
        self._engine = engine
        self._publisher = publisher
        self._outbox: Table = make_tables(schema)[0]
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff

    async def run_once(self) -> RelayStats:
        o = self._outbox
        sent = failed = dead = 0
        async with self._engine.connect() as conn, conn.begin():
            rows = (
                await conn.execute(
                    select(o.c.id, o.c.event_id, o.c.routing_key, o.c.envelope, o.c.attempts)
                    .where(and_(o.c.sent_at.is_(None), o.c.failed_at.is_(None),
                                o.c.next_attempt_at <= func.now()))
                    .order_by(o.c.id)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                body = json.dumps(row.envelope, ensure_ascii=False,
                                  separators=(",", ":")).encode()
                try:
                    await self._publisher.publish(routing_key=row.routing_key, body=body,
                                                  message_id=str(row.event_id))
                except Exception as exc:
                    attempts = row.attempts + 1
                    values: dict[str, object] = {"attempts": attempts,
                                                 "last_error": repr(exc)[:2000]}
                    if attempts >= self._max_attempts:
                        values["failed_at"] = func.now()
                        dead += 1
                        logger.error("Outbox xabari yuborilmadi, to‘xtatildi",
                                     extra={"event_id": str(row.event_id)})
                    else:
                        # Vaqt DB soatidan olinadi: host va DB soati farqi ta’sir qilmaydi.
                        values["next_attempt_at"] = func.now() + self._backoff(attempts)
                        failed += 1
                    await conn.execute(update(o).where(o.c.id == row.id).values(**values))
                    continue
                await conn.execute(update(o).where(o.c.id == row.id).values(sent_at=func.now()))
                sent += 1
        return RelayStats(sent=sent, failed_attempts=failed, dead=dead)

    async def run_forever(self, stop: asyncio.Event, *, idle_interval: float = 0.5) -> None:
        while not stop.is_set():
            try:
                stats = await self.run_once()
            except Exception:
                logger.exception("Outbox relay iteratsiyasi yiqildi")
                stats = RelayStats(0, 0, 0)
            if stats.sent == 0:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=idle_interval)
                except TimeoutError:
                    pass

    async def pending_age_seconds(self) -> float:
        """Kuzatuv uchun: eng eski yuborilmagan yozuv yoshi (TZ 13.13 outbox age)."""
        o = self._outbox
        async with self._engine.connect() as conn:
            age = (await conn.execute(
                select(func.extract("epoch", func.now() - func.min(o.c.created_at)))
                .where(o.c.sent_at.is_(None), o.c.failed_at.is_(None))
            )).scalar()
        return 0.0 if age is None else float(age)

    async def purge_sent(self, older_than: timedelta) -> int:
        o = self._outbox
        async with self._engine.connect() as conn, conn.begin():
            result = await conn.execute(
                delete(o).where(o.c.sent_at < func.now() - older_than)
            )
        return int(result.rowcount or 0)

    def _backoff(self, attempts: int) -> timedelta:
        backoff: timedelta = self._base_backoff * (2 ** (attempts - 1))
        return min(backoff, self._max_backoff)
