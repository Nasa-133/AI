"""file_import: real Postgres + S3 + kontrakt schema’lari bilan to‘liq oqim."""

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from abo_messaging import InboxProcessor, Outcome, new_envelope
from jsonschema import Draft202012Validator, FormatChecker
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
from integration_runtime.ports.connector import ObjectRef

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[4]
CSV = ROOT / "fixtures/synthetic/demo/sotuvlar.csv"
EXPECTED = json.loads((ROOT / "fixtures/synthetic/demo/expected.json").read_text("utf-8"))


def schema(kind: str, name: str) -> Draft202012Validator:
    data = json.loads((ROOT / f"contracts/{kind}/{name}.v1.json").read_text("utf-8"))
    return Draft202012Validator(data, format_checker=FormatChecker())


async def outbox(engine: AsyncEngine, tenant: UUID) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT envelope FROM messaging.outbox WHERE tenant_id = :t ORDER BY id"),
            {"t": tenant})).scalars().all()
    return list(rows)


async def test_discover_configure_sync(engine: AsyncEngine, storage: S3Storage) -> None:
    tenant, source, user = uuid4(), uuid4(), uuid4()
    key = f"uploads/{tenant}/{uuid4()}/sotuvlar.csv"
    await storage.upload(bucket="abo-business", key=key, path=CSV, content_type="text/csv")
    ref = ObjectRef("abo-business", key, hashlib.sha256(CSV.read_bytes()).hexdigest(),
                    CSV.stat().st_size)
    ref_json = {"bucket": ref.bucket, "key": ref.key, "checksum_sha256": ref.checksum_sha256,
                "size_bytes": ref.size_bytes}

    connectors = {"file_import": FileImportConnector(storage)}
    messages = MessageHandlers(CommandHandlers(connectors))
    processor = InboxProcessor(engine, consumer=QUEUE, handlers=messages.routes(),
                               on_transaction_start=messages.on_transaction_start)

    async def send(event_type: str, payload: dict[str, Any]) -> None:
        env = new_envelope(event_type=event_type, producer="business", tenant_id=tenant,
                           aggregate_id=source, aggregate_version=1, payload=payload)
        assert await processor.process(env.to_json(), attempt=1, max_attempts=3) is Outcome.PROCESSED

    # 1) Discover → mapping taklifi
    await send("DiscoverSchema.v1", {"discovery_id": str(uuid4()), "data_source_id": str(source),
                                     "connector_id": "file_import", "object_ref": ref_json,
                                     "requested_by": str(user)})
    discovered = (await outbox(engine, tenant))[-1]
    schema("events", "SchemaDiscovered").validate(discovered["payload"])
    entity = discovered["payload"]["entities"][0]
    assert entity["entity"] == "sales.order_line" and entity["match_score"] == 1.0

    # 2) Tasdiqlangan mapping
    status_map = [{"source_value": k, "canonical_value": v} for k, v in
                  {"tasdiqlangan": "confirmed", "qoralama": "draft",
                   "bekor qilingan": "cancelled"}.items()]
    await send("ConfigureSource.v1", {
        "data_source_id": str(source), "connector_id": "file_import", "mapping_version": 1,
        "entity": "sales.order_line",
        "config": {"delimiter": ",", "encoding": "utf-8", "status_map": status_map},
        "mapping": entity["suggested_mapping"], "approved_by": str(user),
        "approved_at": "2026-09-27T10:00:00+00:00"})
    configured = (await outbox(engine, tenant))[-1]
    schema("events", "SourceConfigured").validate(configured["payload"])
    assert configured["payload"]["accepted"] is True, configured["payload"]

    # 3) Sync: handler faqat navbatga qo‘yadi, runner bajaradi
    run_id = uuid4()
    sync_payload = {"sync_run_id": str(run_id), "data_source_id": str(source),
                    "connector_id": "file_import", "mode": "full", "object_ref": ref_json,
                    "requested_by": str(user), "mapping_version": 1}
    await send("SyncSource.v1", sync_payload)
    await send("SyncSource.v1", sync_payload)  # takroriy command — ikkinchi run yo‘q
    runner = SyncRunner(uow_factory=SqlUnitOfWorkFactory(engine), connectors=connectors,
                        engine=SyncEngine(storage, bucket="abo-integration"), clock=SystemClock(),
                        owner="test")
    while await runner.run_once():
        pass

    events = {e["event_type"]: e for e in await outbox(engine, tenant)}
    ready, done = events["SourceBatchReady.v1"]["payload"], events["SyncRunCompleted.v1"]["payload"]
    schema("events", "SourceBatchReady").validate(ready)
    schema("events", "SyncRunCompleted").validate(done)

    bad_dates = EXPECTED["scenarios"]["quarantine_expected"]["sotuvlar.csv"]["invalid_date"]
    total_rows = EXPECTED["row_counts"]["sotuvlar.csv"]
    assert done["rejected_count"] == len(bad_dates)
    assert sorted(s["source_id"] for s in done["rejection_samples"]) == sorted(bad_dates)
    assert ready["record_count"] == total_rows - len(bad_dates)
    assert done["status"] == "partial" and ready["is_full_snapshot"] is True

    # Canonical fayl: checksum mos, har satr kontraktga mos
    tmp = Path("/tmp") / f"{run_id}.jsonl"
    await storage.download_to(ObjectRef(**ready["object_ref"]), tmp)
    validator = schema("canonical", "sales/order_line")
    lines = tmp.read_text("utf-8").splitlines()
    tmp.unlink()
    assert len(lines) == ready["record_count"]
    for line in lines[:500]:
        validator.validate(json.loads(line))

    # Idempotentlik: bitta batch, command dedup
    async with engine.connect() as conn:
        await conn.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(tenant)})
        runs = (await conn.execute(text("SELECT count(*) FROM integration.sync_runs"))).scalar()
        batches = (await conn.execute(text("SELECT count(*) FROM integration.batches"))).scalar()
    assert (runs, batches) == (1, 1)


async def test_rls_hides_other_tenants(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT set_config('app.tenant_id', :t, false)"),
                           {"t": str(uuid4())})
        for table in ("data_sources", "source_mappings", "sync_runs", "batches"):
            count = (await conn.execute(text(f"SELECT count(*) FROM integration.{table}"))).scalar()
            assert count == 0, table


async def test_sync_without_mapping_fails_cleanly(engine: AsyncEngine, storage: S3Storage) -> None:
    tenant, source = uuid4(), uuid4()
    connectors = {"file_import": FileImportConnector(storage)}
    messages = MessageHandlers(CommandHandlers(connectors))
    processor = InboxProcessor(engine, consumer=QUEUE, handlers=messages.routes(),
                               on_transaction_start=messages.on_transaction_start)
    env = new_envelope(event_type="SyncSource.v1", producer="business", tenant_id=tenant,
                       aggregate_id=source, aggregate_version=1, payload={
                           "sync_run_id": str(uuid4()), "data_source_id": str(source),
                           "connector_id": "file_import", "mode": "full", "object_ref": None,
                           "requested_by": str(uuid4()), "mapping_version": 7})
    assert await processor.process(env.to_json(), attempt=1, max_attempts=3) is Outcome.PROCESSED
    runner = SyncRunner(uow_factory=SqlUnitOfWorkFactory(engine), connectors=connectors,
                        engine=SyncEngine(storage, bucket="abo-integration"), clock=SystemClock(),
                        owner="test")
    while await runner.run_once():
        pass
    failed = [e for e in await outbox(engine, tenant) if e["event_type"] == "SyncRunFailed.v1"]
    assert len(failed) == 1
    schema("events", "SyncRunFailed").validate(failed[0]["payload"])
    assert failed[0]["payload"]["error_code"] == "mapping_invalid"
