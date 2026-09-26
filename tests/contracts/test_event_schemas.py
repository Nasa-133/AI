"""Kontrakt schema’lari o‘zi to‘g‘ri va fixture’lar ularga mos (TZ 13.11, 13.15 gate 3)."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SCHEMAS = sorted(CONTRACTS.rglob("*.v[0-9]*.json"))
SCHEMAS = [p for p in SCHEMAS if "fixtures" not in p.parts]


def load(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize("schema_path", SCHEMAS, ids=lambda p: p.name)
def test_schema_is_valid_draft_2020_12(schema_path: Path) -> None:
    Draft202012Validator.check_schema(load(schema_path))


@pytest.mark.parametrize(
    "fixture_path",
    sorted(CONTRACTS.rglob("fixtures/*.valid.json")),
    ids=lambda p: p.name,
)
def test_valid_fixture_matches_schema(fixture_path: Path) -> None:
    schema_name = fixture_path.name.replace(".valid.json", ".json")
    schema = load(fixture_path.parent.parent / schema_name)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(load(fixture_path))


def test_envelope_rejects_unknown_fields_and_bad_event_type() -> None:
    schema = load(CONTRACTS / "events/envelope.v1.json")
    fixture = load(CONTRACTS / "events/fixtures/envelope.v1.valid.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert not validator.is_valid({**fixture, "extra": 1})
    assert not validator.is_valid({**fixture, "event_type": "dataset_published"})
    assert not validator.is_valid({k: v for k, v in fixture.items() if k != "tenant_id"})
