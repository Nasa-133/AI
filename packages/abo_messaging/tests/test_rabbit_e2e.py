"""Haqiqiy RabbitMQ: outbox → broker → consumer; retry navbati va DLQ."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from abo_messaging import Envelope, InboxProcessor, OutboxRelay, enqueue, new_envelope
from abo_messaging.rabbit import RabbitConsumer, RabbitPublisher, RetryPolicy, connect

pytestmark = pytest.mark.integration

AMQP_URL = os.environ.get("ABO_TEST_AMQP_URL", "amqp://abo:abo_dev@localhost:5672/")


def letters() -> str:
    return "".join(chr(ord("a") + int(c, 16)) for c in uuid4().hex[:8])


async def wait_until(predicate) -> None:  # type: ignore[no-untyped-def]
    async with asyncio.timeout(10):
        while not await predicate():  # noqa: ASYNC110 - tashqi holat (DB/broker) kutiladi
            await asyncio.sleep(0.1)


async def test_outbox_to_consumer_with_retry_and_dlq(db: AsyncEngine) -> None:
    try:
        connection = await connect(AMQP_URL)
    except Exception as exc:  # pragma: no cover - muhitga bog‘liq
        pytest.skip(f"RabbitMQ tayyor emas: {exc}")

    event_type = f"EtoeTest{letters()}.v1"
    poison_type = f"EtoePoison{letters()}.v1"
    attempts: dict[str, int] = {}

    async def flaky(conn: AsyncConnection, env: Envelope) -> None:
        key = str(env.event_id)
        attempts[key] = attempts.get(key, 0) + 1
        if attempts[key] == 1:
            raise TimeoutError("birinchi urinish yiqiladi")
        await conn.execute(text("INSERT INTO public.effects VALUES (:id, 'ok')"),
                           {"id": env.event_id})

    async def poison(conn: AsyncConnection, env: Envelope) -> None:
        raise TimeoutError("har doim yiqiladi")

    queue = f"test.{uuid4().hex[:8]}"
    processor = InboxProcessor(db, consumer=queue,
                               handlers={event_type: flaky, poison_type: poison})
    consumer = RabbitConsumer(connection, processor, queue=queue,
                              retry=RetryPolicy(max_attempts=2, base_delay_ms=200))
    await consumer.start()

    async with db.connect() as conn, conn.begin():
        for et in (event_type, poison_type):
            await enqueue(conn, new_envelope(event_type=et, producer="business",
                                             tenant_id=uuid4(), aggregate_id=uuid4(),
                                             aggregate_version=1, payload={}))
    relay = OutboxRelay(db, RabbitPublisher(connection), base_backoff=timedelta(0))
    assert (await relay.run_once()).sent == 2

    async def processed() -> bool:
        async with db.connect() as c:
            return bool((await c.execute(text("SELECT count(*) FROM public.effects"))).scalar())

    await wait_until(processed)
    assert list(attempts.values()) == [2]

    channel = await connection.channel()
    dlq = await channel.declare_queue(f"{queue}.dlq", durable=True, passive=True)

    async def dead_lettered() -> bool:
        return bool((await channel.declare_queue(dlq.name, passive=True)).declaration_result
                    .message_count)

    await wait_until(dead_lettered)
    await connection.close()
