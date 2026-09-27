from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True, slots=True)
class ToolResult:
    """contracts/tools/tool_result.v1.json."""

    status: Literal["ok", "error"]
    data: dict[str, Any] | None
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"status": self.status, "data": self.data, "source_refs": self.source_refs,
                "warnings": self.warnings, "error_code": self.error_code,
                "error_message": self.error_message, "trace_id": self.trace_id}

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "ToolResult":
        return cls(status=raw["status"], data=raw.get("data"),
                   source_refs=list(raw.get("source_refs", [])),
                   warnings=list(raw.get("warnings", [])), error_code=raw.get("error_code"),
                   error_message=raw.get("error_message"), trace_id=str(raw.get("trace_id", "")))


class ToolAuthError(Exception):
    """Servis tokeni yoki capability rad etildi (401/403) — run davom etmaydi."""


class ToolUnavailable(Exception):
    """Tarmoq/5xx xatosi qayta urinishlardan keyin ham qoldi."""


class BusinessTools(Protocol):
    async def call(self, *, tool_name: str, tool_call_id: str, arguments: dict[str, Any],
                   capability: str, traceparent: str | None) -> ToolResult: ...
