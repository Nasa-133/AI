"""ERP REST API connector: soxta ERP ilovasiga qarshi (tarmoqsiz, ASGI)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from integration_runtime.adapters.connectors import DemoErpConnector
from integration_runtime.adapters.erp_api import RESOURCES, ErpApiConnector
from integration_runtime.application.sync_engine import SyncEngine
from integration_runtime.domain.mapping import SourceConfig, SourceMapping
from integration_runtime.domain.templates import suggest
from integration_runtime.ports.connector import InvalidSource, SourceUnavailable

from .test_connector_conformance import (
    _ERP_DATA,
    DEMO,
    FAKE_ERP_KEY,
    SCHEMAS,
    LocalStorage,
    create_app,
    fake_erp_connector,
    handle,
)


async def no_sleep(_: float) -> None:
    return None


def connector(app: object, key: str = FAKE_ERP_KEY, **kw: object) -> ErpApiConnector:
    return ErpApiConnector("http://erp.test", key, transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
                           sleep=no_sleep, **kw)  # type: ignore[arg-type]


async def test_every_entity_is_suggested_exactly_and_syncs_to_valid_canonical(
        tmp_path: Path) -> None:
    erp = fake_erp_connector()
    discovered = await erp.discover_schema(handle())
    assert [d.source_name for d in discovered] == [f"erp://{r}" for r in RESOURCES.values()]
    storage = LocalStorage(tmp_path)
    engine = SyncEngine(storage, bucket="canonical", work_dir=tmp_path)
    for d in discovered:
        best = suggest(d.columns)[0]
        assert best.match_score == 1.0 and not best.unmapped_required_fields
        mapping = SourceMapping(best.entity, best.mapping,
                                SourceConfig(status_map=best.status_map))
        out = await engine.run(erp, handle(), mapping, sync_run_id=uuid4())
        validator = Draft202012Validator(json.loads(SCHEMAS[best.entity].read_text()),
                                         format_checker=FormatChecker())
        lines = storage.uploaded[out.object_ref.key].splitlines()
        assert len(lines) == out.record_count > 0
        for line in lines[:300]:
            validator.validate(json.loads(line))


async def test_same_history_as_demo_export(tmp_path: Path) -> None:
    """ERP API va demo eksport bir xil tarixiy satrlar va bir xil karantin natijasini beradi."""
    frozen = datetime(2026, 8, 31, 23, 59, tzinfo=UTC)  # faqat tarix (jonli qism hali yo‘q)
    erp = fake_erp_connector(clock=lambda: frozen)
    storage = LocalStorage(tmp_path)
    engine = SyncEngine(storage, bucket="canonical", work_dir=tmp_path)
    for entity, name in (("sales.return", "qaytarishlar.csv"),
                         ("sales.order_line", "sotuvlar.csv")):
        erp_cols = next(d.columns for d in await erp.discover_schema(handle())
                        if suggest(d.columns)[0].entity == entity)
        demo_cols = next(d.columns for d in await DemoErpConnector(DEMO).discover_schema(handle())
                         if d.source_name == name)
        results = []
        for conn, cols in ((erp, erp_cols), (DemoErpConnector(DEMO), demo_cols)):
            best = suggest(cols)[0]
            results.append(await engine.run(
                conn, handle(), SourceMapping(entity, best.mapping,
                                              SourceConfig(status_map=best.status_map)),
                sync_run_id=uuid4()))
        a, b = results
        assert a.record_count == b.record_count > 0
        assert a.rejections.count == b.rejections.count


async def test_bad_key_is_not_retried() -> None:
    app = create_app(data=_ERP_DATA[0], api_key=FAKE_ERP_KEY)
    with pytest.raises(InvalidSource, match="kaliti"):
        await connector(app, key="wrong").discover_schema(handle())


async def test_outage_retries_then_reports_unavailable() -> None:
    now = datetime(2026, 9, 28, 12, tzinfo=UTC)
    app = create_app(data=_ERP_DATA[0], api_key=FAKE_ERP_KEY, clock=lambda: now)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://erp.test") as c:
        r = await c.post("/admin/outage", params={"seconds": 60},
                         headers={"Authorization": f"Bearer {FAKE_ERP_KEY}"})
        assert r.status_code == 200
    slept: list[float] = []

    async def record(delay: float) -> None:
        slept.append(delay)

    erp = ErpApiConnector("http://erp.test", FAKE_ERP_KEY,
                          transport=httpx.ASGITransport(app=app), sleep=record)
    with pytest.raises(SourceUnavailable, match="503"):
        async for _ in erp.read_rows(handle(), "sales.order_line"):
            pass
    assert slept == [5.0, 5.0]  # Retry-After hurmat qilinadi, cheklangan urinish


async def test_rate_limits_are_absorbed() -> None:
    now = datetime(2026, 9, 28, 12, tzinfo=UTC)
    app = create_app(data=_ERP_DATA[0], api_key=FAKE_ERP_KEY, clock=lambda: now, fail_rate=0.3)
    erp = connector(app, attempts=8, page_size=100)
    ids = [row["return_id"] async for _, row in erp.read_rows(handle(), "sales.return")]
    expected = [r["return_id"] for r in _ERP_DATA[0].records("sales-returns", now)]
    assert ids == expected  # 429 lar yutildi, yozuvlar yo‘qolmadi va takrorlanmadi


async def test_cursor_keeps_one_snapshot_while_erp_keeps_posting() -> None:
    """Sinxron o‘rtasida yangi hujjatlar qo‘shilsa ham sahifalar siljimaydi va takrorlanmaydi."""
    moment = [datetime(2026, 9, 28, 6, tzinfo=UTC)]
    app = create_app(data=_ERP_DATA[0], api_key=FAKE_ERP_KEY, clock=lambda: moment[0])
    erp = connector(app, page_size=1000)
    expected = [r["line_id"] for r in _ERP_DATA[0].records("sales-invoice-lines", moment[0])]
    ids: list[str | None] = []
    async for n, row in erp.read_rows(handle(), "sales.order_line"):
        ids.append(row["line_id"])
        if n == 1500:
            moment[0] += timedelta(hours=6)  # ERP ishlashda davom etmoqda
    assert ids == expected  # boshlang‘ich holat: siljish va takror yo‘q
    later = len(_ERP_DATA[0].records("sales-invoice-lines", moment[0]))
    assert later > len(expected)  # keyingi sinxron yangi hujjatlarni oladi


def test_live_days_are_deterministic_and_only_past_is_visible() -> None:
    data = _ERP_DATA[0]
    day = datetime(2026, 9, 15).date()
    assert data.plan(day) == data.plan(day)
    noon = datetime(2026, 9, 15, 7, tzinfo=UTC)  # 12:00 Toshkent
    visible = [r for r in data.records("sales-invoice-lines", noon)
               if str(r["posted_at"]).startswith("2026-09-15")]
    assert visible and all(str(r["posted_at"]) <= "2026-09-15T12:00:00+05:00" for r in visible)
