import hashlib
import json
import math
from typing import Any
from uuid import uuid4

import httpx
import pytest

from ai_runtime.adapters.hash_embedder import HashEmbedder
from ai_runtime.application.embeddings import EmbeddingRequest, generate_embeddings
from ai_runtime.bootstrap.app import create_app
from ai_runtime.bootstrap.settings import Settings
from ai_runtime.ports.embeddings import EmbeddingUnavailable
from tests.fake_core import CONTRACTS, validate


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def test_hash_embedder_is_deterministic_and_similarity_aware() -> None:
    e = HashEmbedder(128)
    a = e.vector("To‘lov muddati 30 kun")
    assert a == e.vector("To'lov muddati 30 kun")  # apostrof variantlari bir xil
    assert len(a) == 128 and abs(sum(x * x for x in a) - 1) < 1e-3
    assert cosine(a, e.vector("to‘lov muddati qancha")) > cosine(a, e.vector("ombor qoldig‘i"))
    assert e.vector("   ") == [1.0] + [0.0] * 127  # nol vektor emas


class MemoryObjects:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put(self, bucket: str, key: str, data: bytes) -> dict[str, Any]:
        self.objects[(bucket, key)] = data
        return {"bucket": bucket, "key": key, "checksum_sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data)}

    async def read_jsonl(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        data = self.objects[(ref["bucket"], ref["key"])]
        if hashlib.sha256(data).hexdigest() != ref["checksum_sha256"]:
            raise ValueError("checksum mos emas")
        return [json.loads(line) for line in data.splitlines() if line.strip()]

    async def put_bytes(self, bucket: str, key: str, data: bytes, *,
                        content_type: str) -> dict[str, Any]:
        return self.put(bucket, key, data)


class BrokenEmbedder(HashEmbedder):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingUnavailable("provider ishlamayapti")


def request(objects: MemoryObjects, chunks: list[dict[str, str]]) -> EmbeddingRequest:
    body = "".join(json.dumps(c) + "\n" for c in chunks).encode()
    ref = objects.put("abo-business", "embeddings-in/x.jsonl", body)
    return EmbeddingRequest(uuid4(), uuid4(), uuid4(), ref, len(chunks))


def check_event(payload: dict[str, Any]) -> None:
    validate(CONTRACTS / "events" / "EmbeddingsGenerated.v1.json", payload)


async def test_generate_embeddings_writes_vectors_in_order() -> None:
    objects = MemoryObjects()
    chunks = [{"chunk_id": str(uuid4()), "text": f"bo‘lim {i} matni"} for i in range(70)]
    req = request(objects, chunks)
    result = await generate_embeddings(req, store=objects, provider=HashEmbedder(64),
                                       bucket="abo-ai")
    check_event(result)
    assert result["status"] == "succeeded" and result["dimensions"] == 64
    rows = await objects.read_jsonl(result["vectors_ref"])
    assert [r["chunk_id"] for r in rows] == [c["chunk_id"] for c in chunks]
    assert result["vectors_ref"]["bucket"] == "abo-ai"


@pytest.mark.parametrize("case", ["checksum", "provider"])
async def test_generate_embeddings_reports_failure(case: str) -> None:
    objects = MemoryObjects()
    req = request(objects, [{"chunk_id": str(uuid4()), "text": "matn"}])
    provider = HashEmbedder(64)
    if case == "checksum":
        objects.objects[("abo-business", "embeddings-in/x.jsonl")] = b'{"tampered": 1}\n'
    else:
        provider = BrokenEmbedder(64)
    result = await generate_embeddings(req, store=objects, provider=provider, bucket="abo-ai")
    check_event(result)
    assert result["status"] == "failed" and result["vectors_ref"] is None
    assert result["error_code"] == ("INVALID_INPUT" if case == "checksum"
                                    else "PROVIDER_UNAVAILABLE")


async def test_embed_endpoint_requires_token_and_matches_contract() -> None:
    app = create_app(Settings(business_tools_token="s" * 40))
    transport = httpx.ASGITransport(app=app)
    body = {"texts": ["to‘lov muddati"], "model_profile": "embedding_default"}
    validate(CONTRACTS / "http" / "ai_runtime.embed.request.v1.json", body)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.post("/internal/v1/embed", json=body)).status_code == 401
        bad = await c.post("/internal/v1/embed", json=body,
                           headers={"Authorization": "Bearer wrong"})
        assert bad.status_code == 401
        ok = await c.post("/internal/v1/embed", json=body,
                          headers={"Authorization": "Bearer " + "s" * 40})
        assert ok.status_code == 200
        validate(CONTRACTS / "http" / "ai_runtime.embed.response.v1.json", ok.json())
        too_many = await c.post("/internal/v1/embed", json={**body, "texts": ["a"] * 17},
                                headers={"Authorization": "Bearer " + "s" * 40})
        assert too_many.status_code == 422


async def test_embed_endpoint_closed_without_configured_token() -> None:
    transport = httpx.ASGITransport(app=create_app(Settings(business_tools_token="")))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/internal/v1/embed", headers={"Authorization": "Bearer "},
                         json={"texts": ["x"], "model_profile": "embedding_default"})
        assert r.status_code == 401
