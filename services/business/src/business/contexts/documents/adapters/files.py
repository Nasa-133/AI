"""FileStore va QueryEmbedder portlari: S3 ombori va AI Runtime embed API (sinxron, 2 s)."""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from business.platform.storage import ObjectRef, S3ObjectStorage

logger = logging.getLogger(__name__)
EMBED_TIMEOUT_SECONDS = 2.0


class S3FileStore:
    def __init__(self, storage: S3ObjectStorage, bucket: str) -> None:
        self._storage, self._bucket = storage, bucket

    async def put_file(self, key: str, path: Path, *, content_type: str) -> dict[str, Any]:
        return (await self._storage.put_file(self._bucket, key, path,
                                             content_type=content_type)).to_json()

    async def download(self, ref: dict[str, Any], path: Path) -> None:
        await self._storage.download_to(ObjectRef.from_json(ref), path)

    async def read_jsonl(self, ref: dict[str, Any]) -> list[dict[str, Any]]:
        return [json.loads(line) async for line in
                self._storage.read_lines(ObjectRef.from_json(ref))]

    async def delete(self, bucket: str, key: str) -> None:
        await self._storage.delete(bucket, key)


class HttpQueryEmbedder:
    """Core → AI yagona sinxron chaqiruv (13.3). Xato — None: qidiruv matnli rejimga tushadi."""

    def __init__(self, base_url: str, token: str, *,
                 redact: Callable[[str], str] = lambda text: text) -> None:
        self._url = base_url.rstrip("/") + "/internal/v1/embed"
        self._token = token
        self._redact = redact  # TZ 13.12: so‘rovdagi shaxsiy ma’lumot AI’ga ketmaydi

    async def embed(self, text: str) -> list[float] | None:
        if not self._url.startswith("http"):
            return None
        try:
            async with httpx.AsyncClient(timeout=EMBED_TIMEOUT_SECONDS) as client:
                r = await client.post(self._url, headers={"Authorization": f"Bearer {self._token}"},
                                      json={"texts": [self._redact(text)[:4000]],
                                            "model_profile": "embedding_default"})
            r.raise_for_status()
            vector: list[float] = r.json()["embeddings"][0]
            return vector
        except (httpx.HTTPError, KeyError, ValueError):
            logger.warning("Query embedding olinmadi — to‘liq matnli qidiruv", exc_info=True)
            return None
