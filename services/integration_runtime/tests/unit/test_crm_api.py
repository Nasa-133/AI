"""CRM REST connector: soxta CRM ilovasiga qarshi (tarmoqsiz, ASGI)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from integration_runtime.adapters.erp_api import CrmApiConnector
from integration_runtime.application.sync_engine import SyncEngine
from integration_runtime.domain.mapping import SourceConfig, SourceMapping
from integration_runtime.domain.templates import suggest
from integration_runtime.ports.connector import InvalidSource

from .test_connector_conformance import (
    _CRM_DATA,
    FAKE_CRM_KEY,
    SCHEMAS,
    LocalStorage,
    create_crm_app,
    fake_crm_connector,
    handle,
)


async def test_deals_are_suggested_exactly_and_sync_to_valid_canonical(tmp_path: Path) -> None:
    crm = fake_crm_connector()
    (discovered,) = await crm.discover_schema(handle())
    assert discovered.source_name == "crm://deals"
    best = suggest(discovered.columns)[0]
    assert best.entity == "crm.deal" and best.match_score == 1.0
    storage = LocalStorage(tmp_path)
    out = await SyncEngine(storage, bucket="canonical", work_dir=tmp_path).run(
        crm, handle(), SourceMapping("crm.deal", best.mapping,
                                     SourceConfig(status_map=best.status_map)),
        sync_run_id=uuid4())
    assert out.rejections.count == 0 and out.record_count > 1000
    validator = Draft202012Validator(json.loads(SCHEMAS["crm.deal"].read_text()),
                                     format_checker=FormatChecker())
    for line in storage.uploaded[out.object_ref.key].splitlines()[:300]:
        record = json.loads(line)
        validator.validate(record)
        assert (record["closed_at"] is None) == (record["status"] == "open")


async def test_deals_progress_over_time() -> None:
    """Haqiqiy CRM kabi: bir oyda ochiq bo‘lgan bitim keyinroq yopiladi (source_revision o‘zgaradi)."""
    early, late = datetime(2026, 3, 10, 7, tzinfo=UTC), datetime(2026, 9, 28, 7, tzinfo=UTC)
    data = _CRM_DATA[0]
    before = {r["deal_id"]: r for r in data.records("deals", early)}
    after = {r["deal_id"]: r for r in data.records("deals", late)}
    assert set(before) < set(after)  # yangi lidlar qo‘shildi
    moved = [d for d, r in before.items() if r["state"] == "open" and after[d]["state"] != "open"]
    assert moved and all(after[d]["updated_at"] != before[d]["updated_at"] for d in moved)
    assert all(after[d]["created_at"] == before[d]["created_at"] for d in before)


async def test_bad_key_is_rejected() -> None:
    app = create_crm_app(data=_CRM_DATA[0], api_key=FAKE_CRM_KEY)
    crm = CrmApiConnector("http://crm.test", "wrong", transport=httpx.ASGITransport(app=app))
    with pytest.raises(InvalidSource, match="CRM kaliti"):
        await crm.discover_schema(handle())
