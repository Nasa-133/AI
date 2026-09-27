"""Modelga beriladigan vosita ta’riflari: `contracts/tools/*.args.v1.json` nusxasi.

Image’ga `contracts/` kirmagani uchun schema’lar paket ichida; mosligi test bilan tekshiriladi
(tests/unit/test_tool_catalog.py).
"""

import json
from importlib import resources
from typing import Any

from ..ports.model import ToolSpec

_META_KEYS = ("$schema", "$id", "title", "description")


def _parameters(schema: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in schema.items() if k not in _META_KEYS}


def load_tool_specs() -> dict[str, ToolSpec]:
    specs: dict[str, ToolSpec] = {}
    for entry in resources.files(__package__).joinpath("tool_schemas").iterdir():
        if not entry.name.endswith(".args.v1.json"):
            continue
        schema = json.loads(entry.read_text(encoding="utf-8"))
        name = entry.name.removesuffix(".args.v1.json")
        specs[name] = ToolSpec(name=name, description=str(schema.get("description", name)),
                               parameters=_parameters(schema))
    return specs
