"""OpenAI adapteri faqat mock klient bilan tekshirilgan (haqiqiy API kalitsiz sinalmagan)."""

from typing import Any

import pytest
from openai.types.responses import Response

from ai_runtime.adapters.openai_provider import OpenAIResponsesProvider
from ai_runtime.ports.model import ModelRequest, ToolSpec


def response(output: list[dict[str, Any]], status: str = "completed",
             incomplete: dict[str, Any] | None = None) -> Response:
    return Response.model_validate({
        "id": "resp_1", "created_at": 0, "object": "response", "model": "m",
        "output": output, "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
        "status": status, "incomplete_details": incomplete,
        "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 3}},
    })


class FakeResponses:
    def __init__(self, reply: Response) -> None:
        self.reply = reply
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Response:
        self.kwargs = kwargs
        return self.reply


class FakeClient:
    def __init__(self, reply: Response) -> None:
        self.responses = FakeResponses(reply)


REQUEST = ModelRequest(instructions="sys", items=[{"type": "message", "role": "user",
                                                   "content": "savdo"}],
                       tools=[ToolSpec("list_available_metrics", "d", {"type": "object"})])


def provider(reply: Response) -> tuple[OpenAIResponsesProvider, FakeClient]:
    client = FakeClient(reply)
    return OpenAIResponsesProvider(api_key="k", model="cfg-model", client=client), client  # type: ignore[arg-type]


async def test_tool_call_and_reasoning_are_kept() -> None:
    p, client = provider(response([
        {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "ENC"},
        {"type": "function_call", "id": "fc_1", "call_id": "call_1",
         "name": "list_available_metrics", "arguments": '{"subject":"all"}'},
    ]))
    out = await p.respond(REQUEST)
    kw = client.responses.kwargs
    assert kw["store"] is False and kw["include"] == ["reasoning.encrypted_content"]
    assert kw["model"] == "cfg-model" and kw["tools"][0]["strict"] is True
    assert "previous_response_id" not in kw
    assert out.tool_calls[0].call_id == "call_1" and out.status == "completed"
    assert out.output_items[0]["encrypted_content"] == "ENC"
    assert (out.input_tokens, out.output_tokens) == (11, 7)


async def test_text_answer() -> None:
    p, _ = provider(response([{"type": "message", "id": "m1", "role": "assistant",
                               "status": "completed", "content": [
                                   {"type": "output_text", "text": "Javob", "annotations": []}]}]))
    out = await p.respond(REQUEST)
    assert out.text == "Javob" and not out.tool_calls


async def test_refusal_and_incomplete() -> None:
    p, _ = provider(response([{"type": "message", "id": "m1", "role": "assistant",
                               "status": "completed",
                               "content": [{"type": "refusal", "refusal": "yo‘q"}]}]))
    assert (await p.respond(REQUEST)).status == "refused"
    p, _ = provider(response([], status="incomplete",
                             incomplete={"reason": "max_output_tokens"}))
    out = await p.respond(REQUEST)
    assert out.status == "incomplete" and "max_output_tokens" in out.limitations[0]


def test_missing_configuration_fails_loudly() -> None:
    with pytest.raises(ValueError, match="yashirin"):
        OpenAIResponsesProvider(api_key="", model="m")
