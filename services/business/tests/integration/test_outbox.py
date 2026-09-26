"""Business DB’dagi outbox app roli bilan ishlaydi va kutubxona shakliga mos (TZ 13.8)."""

from uuid import uuid4

import pytest
from abo_messaging import OutboxRelay, enqueue, new_envelope
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


class RecordingPublisher:
    def __init__(self) -> None:
        self.ids: list[str] = []

    async def publish(self, *, routing_key: str, body: bytes, message_id: str) -> None:
        self.ids.append(message_id)


async def test_outbox_roundtrip_with_app_role(app_engine: AsyncEngine) -> None:
    env = new_envelope(event_type="DatasetSnapshotPublished.v1", producer="business",
                       tenant_id=uuid4(), aggregate_id=uuid4(), aggregate_version=1,
                       payload={"snapshot_id": str(uuid4())})
    async with app_engine.connect() as conn, conn.begin():
        await enqueue(conn, env)
    publisher = RecordingPublisher()
    relay = OutboxRelay(app_engine, publisher, batch_size=1000)
    while (await relay.run_once()).sent:
        pass
    assert str(env.event_id) in publisher.ids
    async with app_engine.connect() as conn:
        sent = (await conn.execute(text(
            "SELECT sent_at IS NOT NULL FROM messaging.outbox WHERE event_id = :id"),
            {"id": env.event_id})).scalar()
    assert sent is True
