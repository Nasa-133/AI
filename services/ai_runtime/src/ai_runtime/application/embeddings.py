"""GenerateEmbeddings: parchalar JSONL → vektorlar JSONL → EmbeddingsGenerated payload (TZ 9.2).

Xato bo‘lsa ham javob qaytadi (status=failed): Business qidiruvni matnli rejimda davom ettiradi.
Ombor vaqtincha ishlamasa istisno yuqoriga chiqadi — broker qayta urinadi.
"""

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ..ports.embeddings import EmbeddingProvider, EmbeddingUnavailable, ObjectStore

BATCH_SIZE = 64
MAX_CHUNKS = 5000
MAX_TEXT_CHARS = 8000


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    tenant_id: UUID
    request_id: UUID
    document_version_id: UUID
    chunks_ref: dict[str, Any]
    chunk_count: int


def _result(req: EmbeddingRequest, *, model: str | None = None, dimensions: int | None = None,
            vectors_ref: dict[str, Any] | None = None, error_code: str | None = None,
            error_message: str | None = None) -> dict[str, Any]:
    return {"request_id": str(req.request_id),
            "document_version_id": str(req.document_version_id),
            "status": "failed" if error_code else "succeeded", "model": model,
            "dimensions": dimensions, "vectors_ref": vectors_ref, "error_code": error_code,
            "error_message": error_message}


async def generate_embeddings(req: EmbeddingRequest, *, store: ObjectStore,
                              provider: EmbeddingProvider, bucket: str) -> dict[str, Any]:
    if req.chunk_count > MAX_CHUNKS:
        return _result(req, error_code="TOO_MANY_CHUNKS",
                       error_message=f"Parchalar soni {MAX_CHUNKS} dan oshdi.")
    try:
        rows = await store.read_jsonl(req.chunks_ref)
        chunks = [(str(r["chunk_id"]), str(r["text"])[:MAX_TEXT_CHARS]) for r in rows]
    except (ValueError, KeyError, TypeError) as exc:
        return _result(req, error_code="INVALID_INPUT", error_message=str(exc)[:1000])
    if not chunks or len(chunks) > MAX_CHUNKS:
        return _result(req, error_code="INVALID_INPUT",
                       error_message="Parchalar fayli bo‘sh yoki limitdan katta.")
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(chunks), BATCH_SIZE):
            vectors += await provider.embed([t for _, t in chunks[start:start + BATCH_SIZE]])
    except EmbeddingUnavailable as exc:
        return _result(req, error_code="PROVIDER_UNAVAILABLE", error_message=str(exc)[:1000])
    body = "".join(json.dumps({"chunk_id": cid, "embedding": vec}) + "\n"
                   for (cid, _), vec in zip(chunks, vectors, strict=True))
    ref = await store.put_bytes(
        bucket, f"embeddings/{req.tenant_id}/{req.document_version_id}/{req.request_id}.jsonl",
        body.encode(), content_type="application/x-ndjson")
    return _result(req, model=provider.model, dimensions=len(vectors[0]), vectors_ref=ref)
