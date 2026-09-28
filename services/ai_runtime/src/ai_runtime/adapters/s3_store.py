"""S3-mos ombor (lokalda SeaweedFS). boto3 sinxron — thread’da ishlatiladi."""

import asyncio
import hashlib
import json
from typing import Any

import boto3
from botocore.config import Config


class S3ObjectStore:
    def __init__(self, *, endpoint_url: str, access_key: str, secret_key: str,
                 region: str = "us-east-1") -> None:
        self._client: Any = boto3.client(
            "s3", endpoint_url=endpoint_url, aws_access_key_id=access_key,
            aws_secret_access_key=secret_key, region_name=region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    async def ensure_bucket(self, bucket: str) -> None:
        def _ensure() -> None:
            try:
                self._client.head_bucket(Bucket=bucket)
            except Exception:
                self._client.create_bucket(Bucket=bucket)

        await asyncio.to_thread(_ensure)

    async def read_jsonl(self, ref: dict[str, object]) -> list[dict[str, object]]:
        def _read() -> bytes:
            body: bytes = self._client.get_object(Bucket=ref["bucket"], Key=ref["key"])[
                "Body"].read()
            return body

        data = await asyncio.to_thread(_read)
        if hashlib.sha256(data).hexdigest() != ref["checksum_sha256"]:
            raise ValueError(f"{ref['key']}: checksum mos emas")
        return [json.loads(line) for line in data.splitlines() if line.strip()]

    async def put_bytes(self, bucket: str, key: str, data: bytes, *,
                        content_type: str) -> dict[str, object]:
        await asyncio.to_thread(self._client.put_object, Bucket=bucket, Key=key, Body=data,
                                ContentType=content_type)
        return {"bucket": bucket, "key": key,
                "checksum_sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
