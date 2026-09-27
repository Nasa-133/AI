"""Shablon + normallashtirish sintetik ERP eksportida (fixtures/synthetic/demo)."""

import csv
import json
from pathlib import Path

import pytest

from integration_runtime.domain.mapping import (
    MappingItem,
    RowRejected,
    SourceConfig,
    SourceMapping,
    Transform,
    normalize_row,
    validate_mapping,
)
from integration_runtime.domain.templates import suggest

DEMO = Path(__file__).resolve().parents[4] / "fixtures/synthetic/demo"
EXPECTED = json.loads((DEMO / "expected.json").read_text(encoding="utf-8"))
FILES = {
    "sotuvlar.csv": "sales.order_line",
    "qaytarishlar.csv": "sales.return",
    "ombor_harakatlari.csv": "inventory.movement",
    "debitorlik.csv": "finance.receivable",
}


def mapping_for(path: Path) -> SourceMapping:
    with path.open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    best = suggest(header)[0]
    return SourceMapping(best.entity, best.mapping, SourceConfig(status_map=best.status_map))


@pytest.mark.parametrize(("name", "entity"), sorted(FILES.items()))
def test_template_recognizes_file_and_mapping_is_valid(name: str, entity: str) -> None:
    with (DEMO / name).open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    best = suggest(header)[0]
    assert best.entity == entity and best.match_score == 1.0
    assert best.unmapped_required_fields == ()
    assert validate_mapping(mapping_for(DEMO / name)) == []


@pytest.mark.parametrize("name", sorted(FILES))
def test_every_row_normalizes_except_invalid_dates(name: str) -> None:
    mapping = mapping_for(DEMO / name)
    rejected: list[str] = []
    count = 0
    with (DEMO / name).open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            count += 1
            try:
                normalize_row(mapping, row)
            except RowRejected:
                rejected.append(next(iter(row.values())) or "")
    expected_bad = EXPECTED["scenarios"]["quarantine_expected"].get(name, {}).get(
        "invalid_date", [])
    # Takrorlar va miqdor ≤ 0 — Core karantini, bu yerda rad etilmaydi.
    assert sorted(rejected) == sorted(expected_bad)
    assert count > 0


def test_unknown_columns_are_not_guessed() -> None:
    suggestions = suggest(["Sana", "Nimadir"])
    assert all(s.match_score < 0.5 for s in suggestions)
    assert any(s.unmapped_required_fields for s in suggestions)


def test_validation_rejects_bad_mapping() -> None:
    mapping = SourceMapping("sales.order_line", (
        MappingItem("source_id", "ID", Transform.DECIMAL),
        MappingItem("amount_includes_vat", None, Transform.CONST, "maybe"),
    ), SourceConfig())
    errors = validate_mapping(mapping)
    assert errors and any("source_id" in e for e in errors)
