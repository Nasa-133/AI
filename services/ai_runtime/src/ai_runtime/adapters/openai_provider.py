"""OpenAI Responses API adapteri (TZ 10).

- `store=False`: suhbat holati bizning checkpoint’da; `previous_response_id` ishlatilmaydi.
- `include=["reasoning.encrypted_content"]`: reasoning elementlari checkpoint’da saqlanib,
  keyingi so‘rovga o‘zgarishsiz qaytariladi.
- Function tool’lar `strict=True`, schema’lar `contracts/tools/*.args.v1.json`.
- Xato bo‘lsa fake javobga yashirin o‘tish yo‘q: istisno runner’ga chiqadi.
"""

from typing import Any, Literal

from openai import AsyncOpenAI

from ..ports.model import ModelRequest, ModelResponse, ToolCall


class OpenAIResponsesProvider:
    name = "openai"

    def __init__(self, *, api_key: str, model: str, client: AsyncOpenAI | None = None,
                 max_output_tokens: int | None = None) -> None:
        if not api_key or not model:
            raise ValueError("OpenAI provayderi uchun AI_OPENAI_API_KEY va AI_OPENAI_MODEL_MAIN "
                             "majburiy (fake’ga yashirin o‘tish yo‘q)")
        self._client = client or AsyncOpenAI(api_key=api_key)
        self._model = model
        self._max_output_tokens = max_output_tokens

    async def respond(self, request: ModelRequest) -> ModelResponse:
        tools: Any = [{"type": "function", "name": t.name, "description": t.description,
                       "parameters": t.parameters, "strict": True} for t in request.tools]
        kwargs: dict[str, Any] = {}
        if self._max_output_tokens:
            kwargs["max_output_tokens"] = self._max_output_tokens
        response = await self._client.responses.create(
            model=self._model,
            instructions=request.instructions,
            input=request.items,  # type: ignore[arg-type]
            tools=tools,
            store=False,
            include=["reasoning.encrypted_content"],
            **kwargs,
        )
        output_items: list[dict[str, Any]] = []
        tool_calls: list[ToolCall] = []
        texts: list[str] = []
        refused = False
        for item in response.output:
            data = item.model_dump(exclude_none=True, mode="json")
            if item.type == "function_call":
                tool_calls.append(ToolCall(call_id=data["call_id"], name=data["name"],
                                           arguments_json=data["arguments"]))
            elif item.type == "message":
                for part in data.get("content", []):
                    if part.get("type") == "output_text":
                        texts.append(part["text"])
                    elif part.get("type") == "refusal":
                        refused = True
            output_items.append(data)
        usage = response.usage
        status: Literal["completed", "incomplete", "refused"] = (
            "refused" if refused
            else "incomplete" if response.status == "incomplete" else "completed")
        limitations = []
        if response.incomplete_details is not None:
            limitations.append(f"Model javobi to‘xtadi: {response.incomplete_details.reason}")
        return ModelResponse(
            status=status,
            output_items=output_items,
            text="\n".join(texts) if texts else None,
            tool_calls=tool_calls,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            limitations=limitations,
        )
