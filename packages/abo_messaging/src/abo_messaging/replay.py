"""Operatsion replay (runbook: docs/runbooks/replay.md).

- `replay_outbox`: vaqt oralig‘idagi (ixtiyoriy tur/tenant bo‘yicha) outbox xabarlarini qayta
  yuborishga belgilaydi. Yetkazish at-least-once; consumer’lar `event_id` bo‘yicha dedup qiladi —
  qayta yuborish takroriy ta’sir bermaydi (ADR 004).
- `requeue_dlq`: `<navbat>.dlq` dagi xabarlarni faqat shu consumer navbatiga qaytaradi (boshqa
  consumer’larga qayta tarqatilmaydi), urinishlar hisobi 1 dan boshlanadi.
"""

from datetime import datetime
from uuid import UUID

import aio_pika
from aio_pika.abc import AbstractRobustConnection
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .rabbit import ATTEMPT_HEADER, RETRY_EXCHANGE


async def replay_outbox(engine: AsyncEngine, *, since: datetime, until: datetime | None = None,
                        event_types: list[str] | None = None, tenant_id: UUID | None = None,
                        schema: str = "messaging") -> int:
    async with engine.connect() as conn, conn.begin():
        result = await conn.execute(text(
            f"UPDATE {schema}.outbox SET sent_at = NULL, failed_at = NULL, attempts = 0,"  # noqa: S608
            " last_error = NULL, next_attempt_at = now()"
            " WHERE created_at >= :since AND (CAST(:until AS timestamptz) IS NULL"
            "   OR created_at < :until)"
            " AND (CAST(:types AS text[]) IS NULL OR event_type = ANY(:types))"
            " AND (CAST(:tenant AS uuid) IS NULL OR tenant_id = :tenant)"
            " AND (sent_at IS NOT NULL OR failed_at IS NOT NULL) RETURNING id"),
            {"since": since, "until": until, "types": event_types, "tenant": tenant_id})
        return len(result.all())


async def requeue_dlq(connection: AbstractRobustConnection, queue: str, *,
                      limit: int = 1000) -> int:
    channel = await connection.channel()
    try:
        dlq = await channel.declare_queue(f"{queue}.dlq", durable=True)
        retry_back = await channel.declare_exchange(RETRY_EXCHANGE, aio_pika.ExchangeType.DIRECT,
                                                    durable=True)
        moved = 0
        while moved < limit:
            message = await dlq.get(no_ack=False, fail=False)
            if message is None:
                break
            await retry_back.publish(aio_pika.Message(
                body=message.body, message_id=message.message_id,
                content_type=message.content_type,
                headers={**(message.headers or {}), ATTEMPT_HEADER: 1},
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key=queue)
            await message.ack()
            moved += 1
        return moved
    finally:
        await channel.close()
