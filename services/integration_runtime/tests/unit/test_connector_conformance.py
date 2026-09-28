"""Connector conformance suite (TZ 13.10, 13.15 gate 4; qabul I01, I02).

Har connector — fayl, demo ERP, ERP REST API (tools/fake_erp ilovasiga qarshi) va faqat shu
testda yozilgan “sintetik” connector — bir xil Connector porti kontraktidan o‘tadi. Uchinchi connector uchun Sync Engine, domen, Core,
AI va Web kodida hech narsa o‘zgarmaydi (I01): u faqat portni amalga oshiradi.
I02: CSV import va demo ERP bir xil faylni bir xil kanonik batch’ga aylantiradi (checksum teng).
"""

import csv
import json
import re
import shutil
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from integration_runtime.adapters.connectors import DemoErpConnector, FileImportConnector
from integration_runtime.adapters.erp_api import CrmApiConnector, ErpApiConnector
from integration_runtime.application.sync_engine import SyncEngine
from integration_runtime.domain.mapping import SourceConfig, SourceMapping
from integration_runtime.domain.templates import suggest
from integration_runtime.ports.connector import (
    Connector,
    ConnectorManifest,
    DiscoveredSource,
    ObjectRef,
    RawRow,
    SourceHandle,
)

ROOT = Path(__file__).resolve().parents[4]
DEMO = ROOT / "fixtures/synthetic/demo"
sys.path.insert(0, str(ROOT / "tools"))
from fake_crm.app import create_app as create_crm_app  # noqa: E402
from fake_crm.crm import CrmData  # noqa: E402
from fake_erp.app import create_app  # noqa: E402
from fake_erp.erp import ErpData  # noqa: E402

FAKE_ERP_KEY = "test-erp-key"
_ERP_DATA: list[ErpData] = []


def fake_erp_connector(**app_kwargs: object) -> ErpApiConnector:
    """ERP connector soxta ERP ilovasiga (tarmoqsiz, ASGI) ulangan; ma’lumot bir marta yuklanadi."""
    if not _ERP_DATA:
        _ERP_DATA.append(ErpData.load(DEMO))
    app = create_app(data=_ERP_DATA[0], api_key=FAKE_ERP_KEY, **app_kwargs)  # type: ignore[arg-type]
    return ErpApiConnector("http://erp.test", FAKE_ERP_KEY,
                           transport=httpx.ASGITransport(app=app))
SCHEMAS = {
    "sales.order_line": ROOT / "contracts/canonical/sales/order_line.v1.json",
    "sales.return": ROOT / "contracts/canonical/sales/return.v1.json",
    "inventory.movement": ROOT / "contracts/canonical/inventory/movement.v1.json",
    "finance.receivable": ROOT / "contracts/canonical/finance/receivable.v1.json",
    "crm.deal": ROOT / "contracts/canonical/crm/deal.v1.json",
}
FILES = {"sales.order_line": "sotuvlar.csv", "sales.return": "qaytarishlar.csv",
         "inventory.movement": "ombor_harakatlari.csv", "finance.receivable": "debitorlik.csv"}


class LocalStorage:
    """ObjectStorage porti: kalit → lokal fayl (S3 o‘rniga)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.uploaded: dict[str, bytes] = {}

    async def download_to(self, ref: ObjectRef, path: Path) -> None:
        shutil.copyfile(self.root / ref.key, path)

    async def upload(self, *, bucket: str, key: str, path: Path, content_type: str) -> None:
        self.uploaded[key] = path.read_bytes()  # noqa: ASYNC240 — test ombori


class SyntheticApiConnector:
    """Uchinchi connector (I01): “API” dan JSON yozuvlar — faqat port orqali, core’siz."""

    manifest = ConnectorManifest(
        connector_id="synthetic_api", version="0.1.0", display_name="Sintetik API (test)",
        supported_entities=("sales.order_line",), capabilities=("full-sync",), is_demo=True,
        requires_object_ref=False)

    def __init__(self, rows: list[RawRow]) -> None:
        self._rows = rows

    async def discover_schema(self, source: SourceHandle) -> list[DiscoveredSource]:
        columns = list(self._rows[0])
        return [DiscoveredSource("api://orders", columns,
                                 [[r[c] for c in columns] for r in self._rows[:5]])]

    async def read_rows(self, source: SourceHandle,
                        entity: str) -> AsyncIterator[tuple[int, RawRow]]:
        for i, row in enumerate(self._rows, start=2):
            yield i, dict(row)


FAKE_CRM_KEY = "test-crm-key"
_CRM_DATA: list[CrmData] = []


def fake_crm_connector(**app_kwargs: object) -> CrmApiConnector:
    if not _CRM_DATA:
        _CRM_DATA.append(CrmData.load(DEMO))
    app = create_crm_app(data=_CRM_DATA[0], api_key=FAKE_CRM_KEY, **app_kwargs)  # type: ignore[arg-type]
    return CrmApiConnector("http://crm.test", FAKE_CRM_KEY,
                           transport=httpx.ASGITransport(app=app))


def demo_rows(name: str, limit: int = 400) -> list[RawRow]:
    with (DEMO / name).open(encoding="utf-8") as f:
        return [dict(r) for _, r in zip(range(limit), csv.DictReader(f), strict=False)]


def handle(object_key: str | None = None) -> SourceHandle:
    ref = ObjectRef("uploads", object_key, "0" * 64, 0) if object_key else None
    return SourceHandle(uuid4(), uuid4(), ref, SourceConfig())


def connectors(tmp: Path) -> list[tuple[Connector, SourceHandle, str]]:
    """(connector, manba, entity) — har connector o‘zi qo‘llaydigan birinchi entity bilan."""
    small = tmp / "sotuvlar.csv"
    rows = demo_rows("sotuvlar.csv")
    with small.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    storage = LocalStorage(tmp)
    return [
        (FileImportConnector(storage, work_dir=tmp), handle("sotuvlar.csv"), "sales.order_line"),
        (DemoErpConnector(DEMO), handle(), "sales.return"),
        (SyntheticApiConnector(rows), handle(), "sales.order_line"),
        (fake_erp_connector(), handle(), "sales.order_line"),
        (fake_crm_connector(), handle(), "crm.deal"),
    ]


@pytest.fixture(params=["file_import", "demo_erp", "synthetic_api", "erp_api", "crm_api"])
def subject(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[Connector, SourceHandle, str]:
    return next(c for c in connectors(tmp_path) if c[0].manifest.connector_id == request.param)


def test_manifest_contract(subject: tuple[Connector, SourceHandle, str]) -> None:
    m = subject[0].manifest
    assert re.fullmatch(r"[a-z][a-z0-9_]{2,40}", m.connector_id)
    assert re.fullmatch(r"\d+\.\d+\.\d+", m.version)
    assert m.display_name and m.capabilities
    assert set(m.supported_entities) <= set(SCHEMAS)  # faqat kanonik entity’lar
    if m.is_demo:
        assert "demo" in m.display_name.lower() or "sintetik" in m.display_name.lower()


async def test_discovery_contract(subject: tuple[Connector, SourceHandle, str]) -> None:
    connector, source, _ = subject
    found = await connector.discover_schema(source)
    assert found
    for s in found:
        assert s.columns and len(set(s.columns)) == len(s.columns)
        assert 0 < len(s.sample_rows) <= 20
        assert all(len(row) == len(s.columns) for row in s.sample_rows)


async def test_rows_are_ordered_raw_strings(subject: tuple[Connector, SourceHandle, str]) -> None:
    connector, source, entity = subject
    previous = 0
    async for line, row in connector.read_rows(source, entity):
        assert line > previous  # manbadagi tartib raqami (CSV’da fizik satr, sarlavha — 1)
        previous = line
        assert all(v is None or isinstance(v, str) for v in row.values())  # xom — tip yo‘q
        if line > 60:
            break


async def test_same_engine_produces_valid_canonical_batch(
        subject: tuple[Connector, SourceHandle, str], tmp_path: Path) -> None:
    """Sync Engine connector turidan qat’i nazar bir xil: normallashtirish, rad etish, batch."""
    connector, source, entity = subject
    discovered = await connector.discover_schema(source)
    columns = next(d.columns for d in discovered if suggest(d.columns)[0].entity == entity)
    best = suggest(columns)[0]
    mapping = SourceMapping(entity, best.mapping, SourceConfig(status_map=best.status_map))
    storage = LocalStorage(tmp_path)
    out = await SyncEngine(storage, bucket="canonical", work_dir=tmp_path).run(
        connector, source, mapping, sync_run_id=uuid4())
    validator = Draft202012Validator(json.loads(SCHEMAS[entity].read_text()),
                                     format_checker=FormatChecker())
    records = [json.loads(line) for line in storage.uploaded[out.object_ref.key].splitlines()]
    assert len(records) == out.record_count > 0
    for record in records[:200]:
        validator.validate(record)


async def test_i02_csv_and_demo_erp_give_identical_canonical_batch(tmp_path: Path) -> None:
    shutil.copyfile(DEMO / "qaytarishlar.csv", tmp_path / "qaytarishlar.csv")
    storage = LocalStorage(tmp_path)
    csv_conn = FileImportConnector(storage, work_dir=tmp_path)
    erp = DemoErpConnector(DEMO)
    with (DEMO / "qaytarishlar.csv").open(encoding="utf-8") as f:
        best = suggest(next(csv.reader(f)))[0]
    mapping = SourceMapping("sales.return", best.mapping, SourceConfig(status_map=best.status_map))
    run = uuid4()
    engine = SyncEngine(storage, bucket="canonical", work_dir=tmp_path)
    a = await engine.run(csv_conn, handle("qaytarishlar.csv"), mapping, sync_run_id=run)
    b = await engine.run(erp, handle(), mapping, sync_run_id=run)
    assert a.record_count == b.record_count > 0
    assert a.object_ref.checksum_sha256 == b.object_ref.checksum_sha256  # bayt darajasida bir xil
    assert a.rejections.count == b.rejections.count
    assert [r.reason for r in a.rejections.samples] == [r.reason for r in b.rejections.samples]
