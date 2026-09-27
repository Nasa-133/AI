import json

import httpx
import pytest

from ai_runtime.adapters.http_tools import HttpBusinessTools
from ai_runtime.ports.tools import ToolAuthError, ToolUnavailable
from tests.fake_core import SERVICE_TOKEN, FakeCore


def tools(core: FakeCore, token: str = SERVICE_TOKEN) -> HttpBusinessTools:
    return HttpBusinessTools(base_url="http://core", service_token=token, client=core.client(),
                             backoff_seconds=0)


async def call(t: HttpBusinessTools, call_id: str = "c1"):  # type: ignore[no-untyped-def]
    return await t.call(tool_name="list_available_metrics", tool_call_id=call_id,
                        arguments={"subject": "all"}, capability="cap", traceparent=None)


async def test_ok_result_and_headers() -> None:
    core = FakeCore()
    result = await call(tools(core))
    assert result.status == "ok" and result.data and result.data["timezone"] == "Asia/Tashkent"


async def test_retries_5xx_with_same_tool_call_id() -> None:
    core = FakeCore()
    core.fail_next = [503, 502]
    result = await call(tools(core), "same-id")
    assert result.status == "ok" and core.calls == [
        ("list_available_metrics", "same-id", {"subject": "all"})]


async def test_gives_up_after_attempts() -> None:
    core = FakeCore()
    core.fail_next = [500, 500, 500]
    with pytest.raises(ToolUnavailable):
        await call(tools(core))


async def test_auth_errors_are_fatal() -> None:
    with pytest.raises(ToolAuthError):
        await call(tools(FakeCore(), token="wrong"))


async def test_network_error_is_retried() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("down")
        assert json.loads(request.content)["tool_call_id"] == "c1"
        return FakeCore().handler(request)

    t = HttpBusinessTools(base_url="http://core", service_token=SERVICE_TOKEN,
                          client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                          backoff_seconds=0)
    assert (await call(t)).status == "ok" and attempts == 2


async def test_other_4xx_becomes_error_result() -> None:
    core = FakeCore()
    core.fail_next = [422]
    result = await call(tools(core))
    assert result.status == "error" and result.error_code == "TOOL_HTTP_ERROR"
