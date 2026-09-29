"""Analytics: golden ma’lumot → ingestion → query (TZ A01–A07)."""

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
from business.contexts.analytics.domain.query import InvalidQuery, UnsupportedDimension
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

    # Joriy davrda umuman yozuv yo‘q — nol emas, bo‘sh qiymat va ochiq izoh.
    base, _ = await q.run(ctx(), args(["net_sales"], "2026-07-01", "2026-07-31", ["branch"]))
    compared, _ = await cmp.compare(ctx(), {"query_spec_id": base["query_spec_id"],
                                            "comparison_range": {"from": "2026-04-01",
                                                                 "to": "2026-04-30"}})
    assert compared["rows"] and all(r[-4] is None and r[-2] is None for r in compared["rows"])
    assert any("Joriy davr" in n and "ma’lumot yo‘q" in n for n in compared["notes"])


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


async def test_a03_partial_month_and_mixed_currencies(
    tenant_conn: tuple[AsyncConnection, UUID],
) -> None:
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    records = order_lines(GOLDEN / "sotuvlar.csv")
    records.append({**records[6], "source_id": "S-USD", "currency": "USD",
                    "gross_amount": "40.00", "vat_amount": "0.00", "cost_amount": "10.00"})
    reader = MemoryReader({"o": jsonl(records)})
    await ingest_batch(store, reader, Outbox(), batch(Entity.SALES_ORDER_LINE, "o", uuid4()),
                       timezone="Asia/Tashkent")
    await store.save_metric_settings(MetricSettings(1, {}, uuid4(), datetime.now(UTC)))
    q = QueryService(store)
    mid_april = ctx(date(2026, 4, 15))

    # Yarim oy + ikki valyuta: yig‘indi valyuta bo‘yicha ajratiladi, hech qachon qo‘shilmaydi.
    data, _ = await q.run(mid_april, args(["net_sales"], "2026-04-01", "2026-04-30"))
    assert [c["name"] for c in data["columns"]] == ["currency", "net_sales"]
    assert sorted(data["rows"]) == [["USD", "40.00"], ["UZS", "450.00"]]
    assert data["currency"] is None
    assert "Bir nechta valyuta: natija valyuta bo‘yicha ajratilgan, qo‘shilmagan." in data["notes"]
    assert any(n.startswith("Davr hali tugamagan") for n in data["notes"])
    # Valyuta tanlansa — bitta qator, ajratish izohi yo‘q; tugagan davrda MTD izohi yo‘q.
    uzs, _ = await q.run(mid_april, {**args(["net_sales"], "2026-04-01", "2026-04-30"),
                                     "currency": "UZS"})
    assert uzs["rows"] == [["450.00"]] and uzs["currency"] == "UZS"
    assert not any(n.startswith("Bir nechta valyuta") for n in uzs["notes"])
    march, _ = await q.run(mid_april, args(["net_sales"], "2026-03-01", "2026-03-31"))
    assert not any(n.startswith("Davr hali tugamagan") for n in march["notes"])


class BrokenReader:
    """Kanonik batch o‘qilayotganda uzilish (obyekt oqimi yarim yo‘lda)."""

    async def read(self, object_ref: dict[str, Any], entity: Entity) -> list[dict[str, Any]]:
        raise ConnectionError("S3 oqimi uzildi")


class FailingOutbox(Outbox):
    """Snapshot yozilgandan keyin, commitdan oldin xato — butun tranzaksiya bekor bo‘lishi kerak."""

    async def publish(self, event_type: str, payload: dict[str, Any], *, aggregate_id: UUID,
                      aggregate_version: int) -> None:
        raise RuntimeError("broker/outbox xatosi")


async def test_a05_failed_ingestion_keeps_previous_snapshot(
    tenant_conn: tuple[AsyncConnection, UUID],
) -> None:
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    source = uuid4()
    await load_golden(store, source)
    q = QueryService(store)
    before, _ = await q.run(ctx(), args(["net_sales"], "2026-01-01", "2026-04-30"))
    active = await store.active_snapshots()

    changed = order_lines(GOLDEN / "sotuvlar.csv")[:2]
    for reader, outbox in ((BrokenReader(), Outbox()),
                           (MemoryReader({"o2": jsonl(changed)}), FailingOutbox())):
        # Inbox handler bilan bir xil: bitta tranzaksiya (bu yerda savepoint).
        with pytest.raises((ConnectionError, RuntimeError)):
            async with conn.begin_nested():
                await ingest_batch(store, reader, outbox,
                                   batch(Entity.SALES_ORDER_LINE, "o2", source),
                                   timezone="Asia/Tashkent")

    assert await store.active_snapshots() == active
    after, _ = await q.run(ctx(), args(["net_sales"], "2026-01-01", "2026-04-30"))
    assert after["rows"] == before["rows"] == [["1800.00"]]
    assert after["dataset_snapshot_ids"] == before["dataset_snapshot_ids"]


async def test_several_sources_are_summed_and_duplicate_base_is_not(
    tenant_conn: tuple[AsyncConnection, UUID],
) -> None:
    """Ikki filialning alohida ERP’lari qo‘shiladi; o‘sha bazani qayta ulash ikki marta sanalmaydi."""
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    lines = order_lines(GOLDEN / "sotuvlar.csv")
    tos = [r for r in lines if r["branch_code"] == "TOS"]
    rest = [r for r in lines if r["branch_code"] != "TOS"]
    erp_a, erp_b, copy = uuid4(), uuid4(), uuid4()
    reader = MemoryReader({"a": jsonl(tos), "b": jsonl(rest), "all": jsonl(lines),
                           "r": jsonl(returns(GOLDEN / "qaytarishlar.csv"))})
    for key, source in (("a", erp_a), ("b", erp_b)):
        await ingest_batch(store, reader, Outbox(), batch(Entity.SALES_ORDER_LINE, key, source),
                           timezone="Asia/Tashkent")
    await ingest_batch(store, reader, Outbox(), batch(Entity.SALES_RETURN, "r", erp_a),
                       timezone="Asia/Tashkent")
    await store.save_metric_settings(MetricSettings(1, {}, uuid4(), datetime.now(UTC)))
    q = QueryService(store)
    total = args(["net_sales"], "2026-01-01", "2026-04-30")

    both, _ = await q.run(ctx(), total)
    assert both["rows"] == [["1800.00"]]  # TOS (A) + boshqa filiallar (B)
    assert len((await store.active_snapshots())[Entity.SALES_ORDER_LINE]) == 2

    # O‘sha baza boshqa yo‘l bilan (to‘liq eksport) ulandi — takroriy, hisobga olinmaydi.
    await ingest_batch(store, reader, Outbox(), batch(Entity.SALES_ORDER_LINE, "all", copy),
                       timezone="Asia/Tashkent")
    again, _ = await q.run(ctx(), total)
    assert again["rows"] == [["1800.00"]]
    status = {r["data_source_id"]: r for r in await store.source_status()
              if r["entity"] == "sales.order_line"}
    assert status[copy]["is_active"] is False and status[copy]["duplicate_of_source"] == erp_a
    assert float(status[copy]["overlap"]) >= 0.5

    # Foydalanuvchi to‘liq eksportni tanladi: A va B undan iborat — ular hisobdan chiqadi.
    assert len(await store.activate_source(copy)) == 2
    chosen, _ = await q.run(ctx(), total)
    assert chosen["rows"] == [["1800.00"]]
    active = (await store.active_snapshots())[Entity.SALES_ORDER_LINE]
    chosen_dataset = (await store.dataset_for(copy, Entity.SALES_ORDER_LINE)).id
    assert [snap.dataset_id for snap in active] == [chosen_dataset]


def deal(source_id: str, created: str, status: str, amount: str, branch: str = "TOS",
         closed: str | None = None, stage: str = "Muzokara",
         channel: str | None = "Instagram") -> dict[str, Any]:
    return {"source_id": source_id, "source_revision": None, "deal_number": f"BT-{source_id}",
            "customer_code": "M0001", "customer_name": "Baraka Savdo MChJ", "branch_code": branch,
            "stage": stage, "status": status, "amount": amount, "currency": "UZS",
            "created_at": f"{created}T10:00:00+05:00",
            "closed_at": f"{closed}T12:00:00+05:00" if closed else None, "channel": channel}


async def test_crm_funnel_metrics(tenant_conn: tuple[AsyncConnection, UUID]) -> None:
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    deals = [
        deal("D1", "2026-01-05", "won", "1000", closed="2026-01-20", stage="Yutildi"),
        deal("D2", "2026-01-10", "lost", "500", closed="2026-02-03", stage="Yutqazildi"),
        deal("D3", "2026-01-15", "open", "2000", branch="SAM"),
        deal("D4", "2026-02-01", "won", "3000", branch="SAM", closed="2026-02-10",
             stage="Yutildi", channel="Tavsiya"),
        deal("D5", "2025-12-20", "won", "400", closed="2026-01-02", stage="Yutildi",
             channel=None),
        deal("D6", "2026-01-07", "won", "999"),  # yopilish sanasisiz “yutildi” — karantin
    ]
    snap = await ingest_batch(store, MemoryReader({"d": jsonl(deals)}), Outbox(),
                              batch(Entity.CRM_DEAL, "d", uuid4()), timezone="Asia/Tashkent")
    assert (snap.row_count, snap.quarantined_count) == (5, 1)
    await store.save_metric_settings(MetricSettings(1, {}, uuid4(), datetime.now(UTC)))
    q = QueryService(store)
    jan = ["crm_deals_created", "crm_deals_won", "crm_won_amount", "crm_win_rate"]

    data, _ = await q.run(ctx(), args(jan, "2026-01-01", "2026-01-31"))
    # Yaratilgan — yaratilish sanasi bo‘yicha (D1–D3); yutilgan — yopilish sanasi (D1, D5).
    assert data["rows"] == [["3", "2", "1400.00", "100.00"]]
    feb, _ = await q.run(ctx(), args([*jan, "crm_avg_deal"], "2026-02-01", "2026-02-28"))
    assert feb["rows"] == [["1", "1", "3000.00", "50.00", "3000.00"]]  # D4 yutildi, D2 yutqazildi

    # Yanvar oxiridagi ochiq voronka: D2 (fevralda yopilgan) va D3 (hali ochiq).
    pipe, _ = await q.run(ctx(), args(["crm_pipeline_open"], "2026-01-01", "2026-01-31",
                                      ["branch"]))
    assert {r[0]: r[-1] for r in pipe["rows"]} == {"SAM": "2000.00", "TOS": "500.00"}
    by_channel, _ = await q.run(ctx(), args(["crm_deals_created"], "2025-12-01", "2026-02-28",
                                            ["channel"]))
    assert {r[0]: r[-1] for r in by_channel["rows"]} == {"Instagram": "3", "Tavsiya": "1",
                                                         "—": "1"}
    with pytest.raises(InvalidQuery, match="aralashtirib"):
        await q.run(ctx(), args(["net_sales", "crm_deals_won"], "2026-01-01", "2026-01-31"))
    with pytest.raises(UnsupportedDimension):  # ochiq voronka — davr oxiridagi holat, oylar yo‘q
        await q.run(ctx(), args(["crm_pipeline_open"], "2026-01-01", "2026-03-31", ["month"]))


async def test_top_n_is_ordered_by_metric(tenant_conn: tuple[AsyncConnection, UUID]) -> None:
    conn, tenant = tenant_conn
    store = SqlAnalyticsStore(conn, tenant)
    await load_golden(store, uuid4())
    q = QueryService(store)
    base = args(["net_sales"], "2026-01-01", "2026-04-30", ["branch"])
    top, _ = await q.run(ctx(), {**base, "limit": 2,
                                 "order_by": {"metric_id": "net_sales", "direction": "desc"}})
    assert [r[0] for r in top["rows"]] == ["BUX", "TOS"] and top["truncated"]  # 850 = 850 → kod
    low, _ = await q.run(ctx(), {**base, "limit": 1,
                                 "order_by": {"metric_id": "net_sales", "direction": "asc"}})
    assert [r[0] for r in low["rows"]] == ["NAM"]  # 100
    with pytest.raises(InvalidQuery, match="Saralash"):
        await q.run(ctx(), {**base, "order_by": {"metric_id": "returns", "direction": "desc"}})
