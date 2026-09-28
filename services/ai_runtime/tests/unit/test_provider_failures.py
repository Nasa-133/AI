"""T03: provayder 429/timeout — cheklangan qayta urinish, tushunarli holat, soxta javob yo‘q."""

from datetime import timedelta
from typing import Any

import httpx
import openai
import pytest

from ai_runtime.adapters.fake_provider import FakeProvider
from ai_runtime.adapters.http_tools import HttpBusinessTools
from ai_runtime.adapters.openai_provider import OpenAIResponsesProvider
from ai_runtime.adapters.tool_catalog import load_tool_specs
from ai_runtime.application.runner import AgentRunner
from ai_runtime.domain.run import RunStatus
from ai_runtime.ports.clock import SystemClock
from ai_runtime.ports.model import ModelRequest, ModelResponse, ModelUnavailable
from tests.fake_core import CONTRACTS, SERVICE_TOKEN, FakeCore, validate
from tests.unit.memory_store import MemoryStore
from tests.unit.test_runner import completed, new_run


class Flaky(FakeProvider):
    def __init__(self, failures: int, *, retryable: bool = True) -> None:
        self.failures = failures
        self.retryable = retryable
        self.calls = 0

    async def respond(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise ModelUnavailable("429", retryable=self.retryable, retry_after=1.5)
        return await super().respond(request)


async def drive(provider: FakeProvider) -> tuple[MemoryStore, FakeCore, Any, list[float]]:
    store, core, sleeps = MemoryStore(), FakeCore(), []
    run = new_run("Oktabr savdosi qancha?")
    store.add(run)

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    tools = HttpBusinessTools(base_url="http://core", service_token=SERVICE_TOKEN,
                              client=core.client(), backoff_seconds=0)
    runner = AgentRunner(store=store, provider=provider, tools=tools, tool_specs=load_tool_specs(),
                         clock=SystemClock(), owner="w1", lease=timedelta(seconds=30),
                         model_attempts=3, backoff_seconds=2, sleep=sleep)
    assert await runner.run_once()
    return store, core, store.runs[run.id], sleeps


async def test_transient_429_recovers_after_retry() -> None:
    provider = Flaky(2)
    store, _, run, sleeps = await drive(provider)
    assert run.status is RunStatus.SUCCEEDED
    assert sleeps == [1.5, 1.5]  # Retry-After hurmat qilinadi
    notes = [e.payload["message"] for e in store.events if e.event_type == "AgentRunProgressed.v1"]
    assert any("AI modeli band" in n for n in notes)  # foydalanuvchi holatni ko‘radi


async def test_persistent_429_fails_clearly_without_fake_answer() -> None:
    provider = Flaky(10)
    store, _, run, sleeps = await drive(provider)
    assert run.status is RunStatus.FAILED and provider.calls == 3 and len(sleeps) == 2
    payload = completed(store)
    validate(CONTRACTS / "events" / "AgentRunCompleted.v1.json", payload)
    assert payload["error_code"] == "PROVIDER_UNAVAILABLE"
    assert payload["result_candidate"] is None  # soxta javob yo‘q
    assert "javob bermayapti" in payload["limitations"][0]


async def test_non_retryable_error_fails_once() -> None:
    provider = Flaky(10, retryable=False)
    store, _, _, sleeps = await drive(provider)
    assert provider.calls == 1 and sleeps == []
    assert completed(store)["error_code"] == "PROVIDER_ERROR"


@pytest.mark.parametrize(("status", "retryable"), [(429, True), (500, True), (401, False)])
async def test_openai_errors_are_mapped(status: int, retryable: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"retry-after": "3"},
                              json={"error": {"message": "x"}})

    client = openai.AsyncOpenAI(api_key="k", max_retries=0,
                                http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    provider = OpenAIResponsesProvider(api_key="k", model="m", client=client)
    with pytest.raises(ModelUnavailable) as err:
        await provider.respond(
            ModelRequest("i", [{"type": "message", "role": "user", "content": "x"}], []))
    assert err.value.retryable is retryable
    if status == 429:
        assert err.value.retry_after == 3.0
