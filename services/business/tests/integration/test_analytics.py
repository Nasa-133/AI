"""Analytics: golden ma’lumot → ingestion → query (TZ A01, A02, A04, A06, A07)."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from business.contexts.analytics.adapters.canonical import parse_line
from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.contexts.analytics.application.comparisons import ComparisonService
from business.contexts.analytics.application.ingest import BatchReady, ingest_batch
from business.contexts.analytics.application.queries import (
    NoData,
    QueryContext,
    QueryService,
    SettingsNotApproved,
)
from business.contexts.analytics.domain.ingestion import Entity
from business.contexts.analytics.ports.store import MetricSettings
from business.platform.db import bind_request_context

from .synthetic import ROOT, jsonl, order_lines, returns

pytestmark = pytest.mark.integration
GOLDEN = ROOT / "fixtures/synthetic/golden"


class MemoryReader:
    def __init__(self, batches: dict[str, list[bytes]]) -> None:
        self.batches = batches

    async def read(self, object_ref: dict[str, Any], entity: Entity) -> list[dict[str, Any]]:
        return [parse_line(entity, line, i + 1)
                for i, line in enumerate(self.batches[object_ref["key"]])]


class Outbox:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, event_type: str, payload: dict[str, Any], *, aggregate_id: UUID,
                      aggregate_version: int) -> None:
        self.events.append((event_type, payload))


def batch(entity: Entity, key: str, source: UUID, batch_id: UUID | None = None) -> BatchReady:
    return BatchReady(batch_id or uuid4(), uuid4(), source, entity, {"key": key},
                      datetime.now(UTC), True)


@pytest.fixture
async def tenant_conn(app_engine: AsyncEngine) -> AsyncIterator[tuple[AsyncConnection, UUID]]:
    tenant = uuid4()
    async with app_engine.connect() as conn:
        await conn.begin()
        await bind_request_context(conn, tenant_id=tenant, user_id=None)
        yield conn, tenant
        await conn.rollback()


def ctx(today: date = date(2026, 9, 27)) -> QueryContext:
    return QueryContext(uuid4(), None, today, "Asia/Tashkent")


def args(metrics: list[str], start: str, end: str, dims: list[str] | None = None) -> dict[str, Any]:
    return {"metric_ids": metrics, "date_range": {"from": start, "to": end},
            "dimensions": dims or [], "filters": {}, "currency": None, "limit": None}


async def load_golden(store: SqlAnalyticsStore, source: UUID) -> Outbox:
    reader = MemoryReader({"o": jsonl(order_lines(GOLDEN / "sotuvlar.csv")),
                           "r": jsonl(returns(GOLDEN / "qaytarishlar.csv"))})
    outbox = Outbox()
    await ingest_batch(store, reader, outbox, batch(Entity.SALES_ORDER_LINE, "o", source),
                       timezone="Asia/Tashkent")
    await ingest_batch(store, reader, outbox, batch(Entity.SALES_RETURN, "r", source),
                       timezone="Asia/Tashkent")
    await store.save_metric_settings(MetricSettings(1, {"vat_policy": "exclude"}, uuid4(),
                                                    datetime.now(UTC)))
    return outbox


async def test_a01_golden_numbers(tenant_conn: tuple[AsyncConnection, UUID]) -> None:
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    outbox = await load_golden(store, uuid4())
    assert [e for e, _ in outbox.events] == ["DatasetSnapshotPublished.v1"] * 2
    data, refs = await QueryService(store).run(
        ctx(), args(["net_sales", "gross_profit", "gross_margin", "discounts", "returns"],
                    "2026-01-01", "2026-01-31"))
    assert data["rows"] == [["850.00", "350.00", "41.18", "50.00", "100.00"]]
    assert data["currency"] == "UZS"
    assert {r["kind"] for r in refs} == {"dataset_snapshot", "query_result"}


async def test_a02_a07_growth_rules(tenant_conn: tuple[AsyncConnection, UUID]) -> None:
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    await load_golden(store, uuid4())
    q = QueryService(store)
    cmp = ComparisonService(q)
    base, _ = await q.run(ctx(), args(["net_sales"], "2026-02-01", "2026-02-28", ["branch"]))
    compared, _ = await cmp.compare(ctx(), {"query_spec_id": base["query_spec_id"],
                                            "comparison_range": {"from": "2026-01-01",
                                                                 "to": "2026-01-31"}})
    nam = next(r for r in compared["rows"] if r[0] == "NAM")
    assert nam[2:] == ["100.00", "0.00", "100.00", None]  # A02: foiz yo‘q
    assert any("NAM" in n for n in compared["notes"])

    base, _ = await q.run(ctx(), args(["gross_profit"], "2026-04-01", "2026-04-30"))
    compared, _ = await cmp.compare(ctx(), {"query_spec_id": base["query_spec_id"],
                                            "comparison_range": {"from": "2026-03-01",
                                                                 "to": "2026-03-31"}})
    assert compared["rows"] == [["-50.00", "-100.00", "50.00", None]]  # A07


async def test_a06_contributions(tenant_conn: tuple[AsyncConnection, UUID]) -> None:
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    await load_golden(store, uuid4())
    q = QueryService(store)
    base, _ = await q.run(ctx(), args(["net_sales"], "2026-02-01", "2026-02-28"))
    data, _ = await ComparisonService(q).explain(ctx(), {
        "query_spec_id": base["query_spec_id"], "dimension": "branch", "metric_id": "net_sales",
        "comparison_range": {"from": "2026-01-01", "to": "2026-01-31"}})
    assert data["total_change"] == "-750.00"
    members = {c["member"]: c for c in data["contributions"]}
    assert members["TOS (Toshkent)"]["change"] == "-850.00"
    assert members["NAM (Namangan)"]["change"] == "100.00"
    assert "sababni" in data["notes"][0]


async def test_a04_snapshot_versioning_keeps_old_answers(
    tenant_conn: tuple[AsyncConnection, UUID],
) -> None:
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    source = uuid4()
    await load_golden(store, source)
    q = QueryService(store)
    old, _ = await q.run(ctx(), args(["net_sales"], "2026-01-01", "2026-01-31"))

    records = order_lines(GOLDEN / "sotuvlar.csv")
    records[0]["gross_amount"] = "700.00"  # o‘zgargan satr
    records.pop(1)  # o‘chirilgan satr
    reader = MemoryReader({"o2": jsonl(records)})
    snap = await ingest_batch(store, reader, Outbox(), batch(Entity.SALES_ORDER_LINE, "o2", source),
                              timezone="Asia/Tashkent")
    assert snap.seq == 2 and snap.row_count == 6

    new, _ = await q.run(ctx(), args(["net_sales"], "2026-01-01", "2026-01-31"))
    assert new["rows"] == [["570.00"]]  # (700 − 30 chegirma) − 100 qaytarish; S0000002 yo‘q
    # Eski query’ga taqqoslash eski snapshot bilan — o‘sha raqamlar (A04).
    cmp, _ = await ComparisonService(q).compare(ctx(), {
        "query_spec_id": old["query_spec_id"],
        "comparison_range": {"from": "2026-01-01", "to": "2026-01-31"}})
    assert cmp["rows"][0][0] == "850.00"


async def test_duplicate_batch_is_idempotent_and_quarantine(
    tenant_conn: tuple[AsyncConnection, UUID],
) -> None:
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    records = order_lines(GOLDEN / "sotuvlar.csv")
    records.append({**records[0], "gross_amount": "1.00"})  # takroriy source_id
    records.append({**records[1], "source_id": "BAD", "quantity": "0"})
    reader = MemoryReader({"o": jsonl(records)})
    same = batch(Entity.SALES_ORDER_LINE, "o", uuid4())
    first = await ingest_batch(store, reader, Outbox(), same, timezone="Asia/Tashkent")
    again = await ingest_batch(store, reader, Outbox(), same, timezone="Asia/Tashkent")
    assert first.id == again.id and first.quarantined_count == 3
    assert first.row_count == len(records) - 3


async def test_query_guards(tenant_conn: tuple[AsyncConnection, UUID]) -> None:
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    with pytest.raises(SettingsNotApproved):
        await QueryService(store).run(ctx(), args(["net_sales"], "2026-01-01", "2026-01-31"))
    await store.save_metric_settings(MetricSettings(1, {}, uuid4(), datetime.now(UTC)))
    with pytest.raises(NoData):
        await QueryService(store).run(ctx(), args(["net_sales"], "2026-01-01", "2026-01-31"))
