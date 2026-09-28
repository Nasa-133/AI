"""TZ 13.15 gate 5: commitdan keyin relay yiqilishi, duplicate, retry, DLQ."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from abo_messaging import (
    Envelope,
    InboxProcessor,
    OutboxRelay,
    Outcome,
    PermanentError,
    enqueue,
    new_envelope,
)

pytestmark = pytest.mark.integration


def event(event_type: str = "SourceBatchReady.v1") -> Envelope:
    return new_envelope(event_type=event_type, producer="integration_runtime",
                        tenant_id=uuid4(), aggregate_id=uuid4(), aggregate_version=1,
                        payload={"n": 1})


class FakePublisher:
    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, *, routing_key: str, body: bytes, message_id: str) -> None:
        # Xabar brokerga yetgan, lekin tasdiq relay’ga kelmagan holatni ham modellashtiradi.
        self.published.append((routing_key, body))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("confirm olinmadi")


async def count(engine: AsyncEngine, sql: str) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(sql))).scalar_one())


async def test_rolled_back_transaction_leaves_no_message(db: AsyncEngine) -> None:
    with pytest.raises(RuntimeError):
        async with db.connect() as conn, conn.begin():
            await enqueue(conn, event())
            raise RuntimeError("domain xatosi")
    assert await count(db, "SELECT count(*) FROM messaging.outbox") == 0


async def test_relay_marks_sent_only_after_confirm(db: AsyncEngine) -> None:
    async with db.connect() as conn, conn.begin():
        await enqueue(conn, event())
    publisher = FakePublisher(fail_times=1)
    relay = OutboxRelay(db, publisher, base_backoff=timedelta(0))
    first = await relay.run_once()
    assert (first.sent, first.failed_attempts) == (0, 1)
    assert await count(db, "SELECT count(*) FROM messaging.outbox WHERE sent_at IS NULL") == 1
    second = await relay.run_once()
    assert second.sent == 1
    # Birinchi urinish ham brokerga yetgan bo‘lishi mumkin: at-least-once.
    assert len(publisher.published) == 2


async def test_relay_gives_up_after_max_attempts(db: AsyncEngine) -> None:
    async with db.connect() as conn, conn.begin():
        await enqueue(conn, event())
    relay = OutboxRelay(db, FakePublisher(fail_times=99), base_backoff=timedelta(0),
                        max_attempts=3)
    for _ in range(3):
        await relay.run_once()
    assert await count(db, "SELECT count(*) FROM messaging.outbox WHERE failed_at IS NOT NULL") == 1
    assert (await relay.run_once()).sent == 0


async def test_parallel_relays_do_not_double_publish(db: AsyncEngine) -> None:
    async with db.connect() as conn, conn.begin():
        for _ in range(50):
            await enqueue(conn, event())
    publisher = FakePublisher()
    relays = [OutboxRelay(db, publisher, batch_size=10) for _ in range(4)]
    while await count(db, "SELECT count(*) FROM messaging.outbox WHERE sent_at IS NULL"):
        await asyncio.gather(*(r.run_once() for r in relays))
    ids = [body for _, body in publisher.published]
    assert len(ids) == 50 == len(set(ids))


async def _record(conn: AsyncConnection, env: Envelope) -> None:
    await conn.execute(text("INSERT INTO public.effects VALUES (:id, 'ok')"),
                       {"id": env.event_id})


async def test_duplicate_delivery_is_processed_once(db: AsyncEngine) -> None:
    processor = InboxProcessor(db, consumer="analytics", handlers={"SourceBatchReady.v1": _record})
    body = event().to_json()
    assert await processor.process(body, attempt=1, max_attempts=3) is Outcome.PROCESSED
    assert await processor.process(body, attempt=1, max_attempts=3) is Outcome.DUPLICATE
    assert await count(db, "SELECT count(*) FROM public.effects") == 1
    # Boshqa consumer uchun esa bu yangi xabar.
    other = InboxProcessor(db, consumer="dashboards", handlers={"SourceBatchReady.v1": _record})
    assert await other.process(body, attempt=1, max_attempts=3) is Outcome.PROCESSED


async def test_failed_handler_rolls_back_effects_and_dedup_mark(db: AsyncEngine) -> None:
    calls = 0

    async def flaky(conn: AsyncConnection, env: Envelope) -> None:
        nonlocal calls
        calls += 1
        await _record(conn, env)
        if calls < 3:
            raise TimeoutError("vaqtinchalik")

    processor = InboxProcessor(db, consumer="c", handlers={"SourceBatchReady.v1": flaky})
    body = event().to_json()
    assert await processor.process(body, attempt=1, max_attempts=5) is Outcome.RETRY
    assert await count(db, "SELECT count(*) FROM public.effects") == 0
    assert await count(db, "SELECT count(*) FROM messaging.inbox") == 0
    assert await processor.process(body, attempt=2, max_attempts=5) is Outcome.RETRY
    assert await processor.process(body, attempt=3, max_attempts=5) is Outcome.PROCESSED
    assert await count(db, "SELECT count(*) FROM public.effects") == 1


async def test_dead_letter_cases(db: AsyncEngine) -> None:
    async def permanent(conn: AsyncConnection, env: Envelope) -> None:
        raise PermanentError("schema mos emas")

    async def always_fails(conn: AsyncConnection, env: Envelope) -> None:
        raise TimeoutError

    p = InboxProcessor(db, consumer="c", handlers={"SourceBatchReady.v1": permanent,
                                                   "SyncRunFailed.v1": always_fails})
    assert await p.process(event().to_json(), attempt=1, max_attempts=5) is Outcome.DEAD
    assert await p.process(event("SyncRunFailed.v1").to_json(), attempt=5,
                           max_attempts=5) is Outcome.DEAD
    assert await p.process(event("SourceBatchReady.v2").to_json(), attempt=1,
                           max_attempts=5) is Outcome.DEAD
    assert await p.process(b"{}", attempt=1, max_attempts=5) is Outcome.DEAD


async def test_handler_can_emit_follow_up_atomically(db: AsyncEngine) -> None:
    async def react(conn: AsyncConnection, env: Envelope) -> None:
        await enqueue(conn, new_envelope(
            event_type="DatasetSnapshotPublished.v1", producer="business",
            tenant_id=env.tenant_id, aggregate_id=uuid4(), aggregate_version=1,
            payload={}, correlation_id=env.correlation_id, causation_id=env.event_id))

    p = InboxProcessor(db, consumer="c", handlers={"SourceBatchReady.v1": react})
    source = event()
    await p.process(source.to_json(), attempt=1, max_attempts=3)
    async with db.connect() as conn:
        row = (await conn.execute(text(
            "SELECT envelope->>'causation_id', envelope->>'correlation_id'"
            " FROM messaging.outbox"))).one()
    assert row == (str(source.event_id), str(source.correlation_id))


async def test_replay_republishes_window_and_consumers_dedup(db: AsyncEngine) -> None:
    """Replay mashqi: yuborilgan eventlarni qayta yuborish takroriy ta’sir bermaydi."""
    from abo_messaging import replay_outbox

    # Vaqt oynasi DB soatidan (host va konteyner soati farq qilishi mumkin — ADR 004).
    async with db.connect() as conn:
        start = (await conn.execute(text("SELECT now()"))).scalar_one()
    envelopes = [event() for _ in range(3)]
    async with db.connect() as conn, conn.begin():
        for env in envelopes:
            await enqueue(conn, env)
        await enqueue(conn, event("Other.v1"))
    publisher = FakePublisher()
    relay = OutboxRelay(db, publisher, base_backoff=timedelta(0))
    await relay.run_once()
    processor = InboxProcessor(db, consumer="analytics", handlers={"SourceBatchReady.v1": _record})
    for _, body in publisher.published:
        if b"SourceBatchReady" in body:
            await processor.process(body, attempt=1, max_attempts=3)
    assert await count(db, "SELECT count(*) FROM public.effects") == 3

    replayed = await replay_outbox(db, since=start, event_types=["SourceBatchReady.v1"])
    assert replayed == 3
    publisher.published.clear()
    await relay.run_once()
    assert len(publisher.published) == 3  # faqat tanlangan tur qayta yuborildi
    outcomes = [await processor.process(body, attempt=1, max_attempts=3)
                for _, body in publisher.published]
    assert outcomes == [Outcome.DUPLICATE] * 3
    assert await count(db, "SELECT count(*) FROM public.effects") == 3  # ta’sir takrorlanmadi
