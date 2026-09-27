"""Soxta Core Tool API: `contracts/tools/fixtures` asosida kontraktga mos javoblar."""

import copy
import json
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator, FormatChecker

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
TOOLS = CONTRACTS / "tools"
SERVICE_TOKEN = "test-service-token"


def load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def validate(schema_path: Path, instance: Any) -> None:
    Draft202012Validator(load(schema_path), format_checker=FormatChecker()).validate(instance)


def fixture_data(tool: str) -> dict[str, Any]:
    return copy.deepcopy(load(TOOLS / "fixtures" / f"{tool}.result.v1.valid.json"))


def default_data() -> dict[str, dict[str, Any]]:
    data = {name: fixture_data(name) for name in (
        "list_available_metrics", "run_metric_query", "compare_periods",
        "explain_contributions", "create_dashboard")}
    catalog = data["list_available_metrics"]
    catalog["currencies"] = ["UZS"]
    catalog["metrics"].append({
        "id": "gross_profit", "name": "Yalpi foyda", "description": "Sof savdo − tannarx",
        "unit": "money", "version": 1, "subject": "finance",
        "dimensions": ["month", "branch"], "approved": True})
    return data


class FakeCore:
    """Chaqiruvlarni yozib boradi; `tool_call_id` bo‘yicha dedup qiladi (Core kabi)."""

    def __init__(self, data: dict[str, dict[str, Any]] | None = None) -> None:
        self.data = data or default_data()
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.fail_next: list[int] = []  # navbatdagi so‘rovlar uchun HTTP status
        self.results: dict[str, dict[str, Any]] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail_next:
            return httpx.Response(self.fail_next.pop(0))
        if request.headers.get("Authorization") != f"Bearer {SERVICE_TOKEN}":
            return httpx.Response(401)
        if not request.headers.get("X-ABO-Capability"):
            return httpx.Response(403)
        name = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content)
        validate(TOOLS / "tool_request.v1.json", body)
        validate(TOOLS / f"{name}.args.v1.json", body["arguments"])
        self.calls.append((name, body["tool_call_id"], body["arguments"]))
        if body["tool_call_id"] not in self.results:
            data = self.data[name]
            validate(TOOLS / f"{name}.result.v1.json", data)
            snaps = data.get("dataset_snapshot_ids", [])
            self.results[body["tool_call_id"]] = {
                "status": "ok", "data": data,
                "source_refs": [{"kind": "dataset_snapshot", "id": s, "version_id": None,
                                 "locator": None} for s in snaps],
                "warnings": [], "error_code": None, "error_message": None, "trace_id": "t1"}
        result = self.results[body["tool_call_id"]]
        validate(TOOLS / "tool_result.v1.json", result)
        return httpx.Response(200, json=result)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]
