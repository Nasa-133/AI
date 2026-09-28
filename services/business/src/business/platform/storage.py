"""S3-mos obyekt ombori (lokalda SeaweedFS). boto3 sinxron — alohida thread’da ishlatiladi."""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

import boto3
from botocore.config import Config

from business.kernel.errors import BusinessError


class ChecksumMismatch(BusinessError):
    code = "CHECKSUM_MISMATCH"


class ObjectTooLarge(BusinessError):
    code = "PAYLOAD_TOO_LARGE"


@dataclass(frozen=True, slots=True)
class ObjectRef:
    bucket: str
    key: str
    checksum_sha256: str
    size_bytes: int

    def to_json(self) -> dict[str, Any]:
        return {"bucket": self.bucket, "key": self.key, "checksum_sha256": self.checksum_sha256,
                "size_bytes": self.size_bytes}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ObjectRef":
        return cls(data["bucket"], data["key"], data["checksum_sha256"], int(data["size_bytes"]))


class _HashingReader:
    """Yuklash oqimidan SHA-256 va hajmni hisoblaydi, limit oshsa to‘xtatadi."""

    def __init__(self, source: IO[bytes], max_bytes: int) -> None:
        self._source = source
        self._max = max_bytes
        self.size = 0
        self.sha256 = hashlib.sha256()

    def read(self, n: int = -1) -> bytes:
        chunk = self._source.read(n)
        self.size += len(chunk)
        if self.size > self._max:
            raise ObjectTooLarge(f"Fayl hajmi {self._max // (1024 * 1024)} MB limitdan oshdi.")
        self.sha256.update(chunk)
        return chunk


class S3ObjectStorage:
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

    async def put_stream(self, bucket: str, key: str, source: IO[bytes], *, max_bytes: int,
                         content_type: str) -> ObjectRef:
        reader = _HashingReader(source, max_bytes)
        await asyncio.to_thread(self._client.upload_fileobj, reader, bucket, key,
                                ExtraArgs={"ContentType": content_type})
        return ObjectRef(bucket, key, reader.sha256.hexdigest(), reader.size)

    async def read_lines(self, ref: ObjectRef) -> AsyncIterator[bytes]:
        """Satrma-satr o‘qiydi; oxirida checksum tekshiriladi (mos kelmasa — xato)."""
        response = await asyncio.to_thread(self._client.get_object, Bucket=ref.bucket, Key=ref.key)
        body = response["Body"]
        digest = hashlib.sha256()
        pending = b""
        while True:
            chunk: bytes = await asyncio.to_thread(body.read, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            pending += chunk
            *lines, pending = pending.split(b"\n")
            for line in lines:
                if line.strip():
                    yield line
        if pending.strip():
            yield pending
        if digest.hexdigest() != ref.checksum_sha256:
            raise ChecksumMismatch(f"{ref.key}: checksum mos emas.")

    async def put_file(self, bucket: str, key: str, path: Path, *, content_type: str) -> ObjectRef:
        digest = await asyncio.to_thread(_sha256_file, path)
        await asyncio.to_thread(self._client.upload_file, str(path), bucket, key,
                                ExtraArgs={"ContentType": content_type})
        size = (await asyncio.to_thread(path.stat)).st_size
        return ObjectRef(bucket, key, digest, size)

    async def download_to(self, ref: ObjectRef, path: Path) -> None:
        await asyncio.to_thread(self._client.download_file, ref.bucket, ref.key, str(path))
        if await asyncio.to_thread(_sha256_file, path) != ref.checksum_sha256:
            raise ChecksumMismatch(f"{ref.key}: checksum mos emas.")

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=bucket, Key=key)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
