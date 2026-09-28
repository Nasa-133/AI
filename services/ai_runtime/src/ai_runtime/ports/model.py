from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelRequest:
    instructions: str
    items: list[dict[str, Any]]
    tools: list[ToolSpec]


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """`output_items` — suhbatga qo‘shiladigan elementlar (Responses input formatida,
    reasoning va function_call’lar ham), keyingi so‘rovda o‘zgarishsiz qaytariladi."""

    status: Literal["completed", "incomplete", "refused"]
    output_items: list[dict[str, Any]]
    text: str | None
    tool_calls: list[ToolCall]
    input_tokens: int = 0
    output_tokens: int = 0
    # Model aniqlashtiruvchi savol bilan to‘xtaganini bildiradi (run → partial).
    needs_clarification: bool = False
    limitations: list[str] = field(default_factory=list)


class ModelUnavailable(Exception):
    """Provayder javob bermadi. `retryable` — 429/timeout/5xx; aks holda konfiguratsiya xatosi."""

    def __init__(self, message: str, *, retryable: bool, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class ModelProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def respond(self, request: ModelRequest) -> ModelResponse: ...
