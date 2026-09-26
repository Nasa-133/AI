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


def _fixture_for(schema_path: Path) -> Path:
    return schema_path.parent / "fixtures" / schema_path.name.replace(".json", ".valid.json")


@pytest.mark.parametrize("schema_path", SCHEMAS, ids=lambda p: p.name)
def test_every_schema_has_valid_fixture(schema_path: Path) -> None:
    assert _fixture_for(schema_path).exists(), f"Fixture yo‘q: {_fixture_for(schema_path)}"


def _objects(node: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            found.append(node)
        for value in node.values():
            found.extend(_objects(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_objects(value))
    return found


@pytest.mark.parametrize("schema_path", SCHEMAS, ids=lambda p: p.name)
def test_objects_are_closed_and_fully_required(schema_path: Path) -> None:
    """additionalProperties: false; nullable maydon ham `required` (qiymati null bo‘ladi)."""
    for obj in _objects(load(schema_path)):
        props = obj["properties"]
        assert isinstance(props, dict)
        if obj.get("title") == "Event/command envelope v1":
            continue
        assert obj.get("additionalProperties") is False, schema_path.name
        assert set(obj.get("required", [])) == set(props), (
            f"{schema_path.name}: barcha maydonlar required bo‘lishi kerak"
        )


@pytest.mark.parametrize(
    "schema_path",
    [p for p in SCHEMAS if "canonical" in p.parts],
    ids=lambda p: p.name,
)
def test_money_is_never_a_json_number(schema_path: Path) -> None:
    fixture = load(_fixture_for(schema_path))
    validator = Draft202012Validator(load(schema_path), format_checker=FormatChecker())
    decimal_fields = [
        k for k, v in load(schema_path)["properties"].items()  # type: ignore[union-attr]
        if "Decimal" in json.dumps(v)
    ]
    for name in decimal_fields:
        if fixture.get(name) is not None:
            assert not validator.is_valid({**fixture, name: 12.5}), f"{name} float qabul qildi"
            assert not validator.is_valid({**fixture, name: "1,5"}), f"{name} vergul qabul qildi"


def test_batch_manifest_matches_source_batch_ready() -> None:
    manifest = load(CONTRACTS / "canonical/batch_manifest.v1.json")["properties"]
    event = load(CONTRACTS / "events/SourceBatchReady.v1.json")["properties"]
    assert isinstance(manifest, dict) and isinstance(event, dict)
    assert set(manifest) - set(event) == {"tenant_id", "records_format"}
    for name in event:
        assert manifest[name] == event[name], f"{name} manifest va event’da farq qiladi"
