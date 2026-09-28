"""OpenAI embeddings adapteri. Model nomi konfiguratsiyadan (TZ 10)."""

import openai

from ..ports.embeddings import EmbeddingUnavailable


class OpenAIEmbedder:
    def __init__(self, *, api_key: str, model: str, dimensions: int | None = None,
                 timeout: float = 30.0, client: openai.AsyncOpenAI | None = None) -> None:
        if not model:
            raise ValueError("OPENAI_MODEL_EMBEDDING berilmagan")
        self._client = client or openai.AsyncOpenAI(api_key=api_key, timeout=timeout,
                                                    max_retries=2)
        self._model = model
        self._dims = dimensions

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dims or 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            if self._dims:
                response = await self._client.embeddings.create(
                    model=self._model, input=texts, dimensions=self._dims)
            else:
                response = await self._client.embeddings.create(model=self._model, input=texts)
        except openai.OpenAIError as exc:
            raise EmbeddingUnavailable(f"OpenAI embeddings: {type(exc).__name__}") from exc
        vectors = [list(d.embedding) for d in sorted(response.data, key=lambda d: d.index)]
        if len(vectors) != len(texts):
            raise EmbeddingUnavailable("OpenAI embeddings: vektorlar soni mos emas")
        if not self._dims and vectors:
            self._dims = len(vectors[0])
        return vectors
