"""Business Core Tool API mijozi (contracts/tools, docs/design/stage1.md §6)."""

import asyncio
import logging
from typing import Any

import httpx

from ..ports.tools import ToolAuthError, ToolResult, ToolUnavailable

logger = logging.getLogger(__name__)


class HttpBusinessTools:
    """Tarmoq xatosi va 5xx’da o‘sha `tool_call_id` bilan qayta urinadi (Core dedup qiladi)."""

    def __init__(self, *, base_url: str, service_token: str,
                 client: httpx.AsyncClient | None = None, attempts: int = 3,
                 backoff_seconds: float = 0.5, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip("/")
        self._token = service_token
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._attempts = attempts
        self._backoff = backoff_seconds

    async def call(self, *, tool_name: str, tool_call_id: str, arguments: dict[str, Any],
                   capability: str, traceparent: str | None) -> ToolResult:
        headers = {"Authorization": f"Bearer {self._token}", "X-ABO-Capability": capability}
        if traceparent:
            headers["traceparent"] = traceparent
        body = {"tool_call_id": tool_call_id, "arguments": arguments}
        url = f"{self._base}/internal/v1/tools/{tool_name}"
        last_error = "noma’lum"
        for attempt in range(1, self._attempts + 1):
            try:
                response = await self._client.post(url, json=body, headers=headers)
            except httpx.TransportError as exc:
                last_error = type(exc).__name__
            else:
                if response.status_code in (401, 403):
                    raise ToolAuthError(f"Tool API {response.status_code}")
                if response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                elif response.status_code == 200:
                    return ToolResult.from_json(response.json())
                else:
                    # 4xx (auth’dan tashqari) — kontrakt buzilishi, qayta urinish foydasiz.
                    return ToolResult(status="error", data=None, error_code="TOOL_HTTP_ERROR",
                                      error_message=f"HTTP {response.status_code}")
            logger.warning("Tool API xatosi (%s), urinish %s/%s", last_error, attempt,
                           self._attempts, extra={"tool": tool_name, "tool_call_id": tool_call_id})
            if attempt < self._attempts:
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
        raise ToolUnavailable(last_error)

    async def aclose(self) -> None:
        await self._client.aclose()
