import json

from ai_runtime.adapters.tool_catalog import load_tool_specs
from ai_runtime.domain.roles import KNOWN_TOOLS
from tests.fake_core import TOOLS


def test_bundled_schemas_match_contracts() -> None:
    specs = load_tool_specs()
    assert set(specs) == KNOWN_TOOLS
    for name, spec in specs.items():
        contract = json.loads((TOOLS / f"{name}.args.v1.json").read_text(encoding="utf-8"))
        for key in ("$schema", "$id", "title", "description"):
            contract.pop(key, None)
        assert spec.parameters == contract, f"{name}: paket nusxasi kontraktdan farq qiladi"


def test_parameters_are_strict_mode_compatible() -> None:
    def check(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    for spec in load_tool_specs().values():
        check(spec.parameters)
