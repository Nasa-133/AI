"""A05: ERP sinxroni yarim yo‘lda uziladi — yangi batch e’lon qilinmaydi, oxirgi to‘liq batch qoladi."""

import hashlib
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from abo_messaging import InboxProcessor, Outcome, new_envelope
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from integration_runtime.adapters.connectors import FileImportConnector
from integration_runtime.adapters.s3_storage import S3Storage
from integration_runtime.adapters.sql_uow import SqlUnitOfWorkFactory
from integration_runtime.application.handlers import CommandHandlers
from integration_runtime.application.sync_engine import SyncEngine
from integration_runtime.application.sync_runner import SyncRunner
from integration_runtime.bootstrap.clock import SystemClock
from integration_runtime.entrypoints.messages import QUEUE, MessageHandlers
from integration_runtime.ports.connector import ObjectRef, RawRow, SourceHandle, SourceUnavailable

from .test_file_import_e2e import CSV, outbox, schema

pytestmark = pytest.mark.integration


class InterruptedConnector(FileImportConnector):
    """Birinchi `cut_after` satrdan keyin aloqa uziladi (ERP timeout / tarmoq)."""

    cut_after: int | None = None

    async def read_rows(self, source: SourceHandle,
                        entity: str) -> AsyncIterator[tuple[int, RawRow]]:
        async for n, row in super().read_rows(source, entity):
            if self.cut_after is not None and n > self.cut_after:
                raise SourceUnavailable("ERP ulanishi uzildi")
            yield n, row


async def test_a05_interrupted_sync_keeps_last_full_batch(engine: AsyncEngine,
                                                          storage: S3Storage) -> None:
    tenant, source, user = uuid4(), uuid4(), uuid4()
    key = f"uploads/{tenant}/{uuid4()}/sotuvlar.csv"
    await storage.upload(bucket="abo-business", key=key, path=CSV, content_type="text/csv")
    ref = ObjectRef("abo-business", key, hashlib.sha256(CSV.read_bytes()).hexdigest(),
                    CSV.stat().st_size)
    ref_json = {"bucket": ref.bucket, "key": ref.key, "checksum_sha256": ref.checksum_sha256,
                "size_bytes": ref.size_bytes}
    connector = InterruptedConnector(storage)
    connectors = {"file_import": connector}
    messages = MessageHandlers(CommandHandlers(connectors))
    processor = InboxProcessor(engine, consumer=QUEUE, handlers=messages.routes(),
                               on_transaction_start=messages.on_transaction_start)

    async def send(event_type: str, payload: dict[str, Any]) -> None:
        env = new_envelope(event_type=event_type, producer="business", tenant_id=tenant,
                           aggregate_id=source, aggregate_version=1, payload=payload)
        assert await processor.process(env.to_json(), attempt=1, max_attempts=3) is Outcome.PROCESSED

    await send("DiscoverSchema.v1", {"discovery_id": str(uuid4()), "data_source_id": str(source),
                                     "connector_id": "file_import", "object_ref": ref_json,
                                     "requested_by": str(user)})
    mapping = (await outbox(engine, tenant))[-1]["payload"]["entities"][0]["suggested_mapping"]
    status_map = [{"source_value": k, "canonical_value": v} for k, v in
                  {"tasdiqlangan": "confirmed", "qoralama": "draft",
                   "bekor qilingan": "cancelled"}.items()]
    await send("ConfigureSource.v1", {
        "data_source_id": str(source), "connector_id": "file_import", "mapping_version": 1,
        "entity": "sales.order_line",
        "config": {"delimiter": ",", "encoding": "utf-8", "status_map": status_map},
        "mapping": mapping, "approved_by": str(user), "approved_at": "2026-09-27T10:00:00+00:00"})
    runner = SyncRunner(uow_factory=SqlUnitOfWorkFactory(engine), connectors=connectors,
                        engine=SyncEngine(storage, bucket="abo-integration"), clock=SystemClock(),
                        owner="test", max_attempts=2, retry_delay=timedelta(0))

    async def sync() -> UUID:
        run_id = uuid4()
        await send("SyncSource.v1", {"sync_run_id": str(run_id), "data_source_id": str(source),
                                     "connector_id": "file_import", "mode": "full",
                                     "object_ref": ref_json, "requested_by": str(user),
                                     "mapping_version": 1})
        while await runner.run_once():
            pass
        return run_id

    first = await sync()
    connector.cut_after = 100  # ikkinchi sinxron 100-satrdan keyin uziladi
    second = await sync()

    events = await outbox(engine, tenant)
    ready = [e["payload"] for e in events if e["event_type"] == "SourceBatchReady.v1"]
    failed = [e["payload"] for e in events if e["event_type"] == "SyncRunFailed.v1"]
    # Faqat birinchi (to‘liq) batch e’lon qilingan — Core o‘sha snapshot bilan ishlashda davom etadi.
    assert [p["sync_run_id"] for p in ready] == [str(first)]
    assert len(failed) == 1 and failed[0]["sync_run_id"] == str(second)
    schema("events", "SyncRunFailed").validate(failed[0])
    assert failed[0]["error_code"] == "source_unavailable" and failed[0]["retryable"] is True
    # Qisman ish ko‘rinadi: run “failed” (2 urinishdan keyin); yarim batch yozilmagan.
    async with engine.connect() as conn:
        await conn.execute(text("SELECT set_config('app.tenant_id', :t, false)"),
                           {"t": str(tenant)})
        status = (await conn.execute(text(
            "SELECT status FROM integration.sync_runs WHERE id = :id"), {"id": second})).scalar()
        batches = (await conn.execute(text(
            "SELECT count(*) FROM integration.batches"))).scalar()
    assert status == "failed"
    assert batches == 1
