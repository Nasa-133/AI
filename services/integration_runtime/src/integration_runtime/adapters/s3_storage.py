"""S3-mos ombor (lokalda SeaweedFS). boto3 sinxron — thread’da; fayllar diskka oqim bilan."""

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

from ..ports.connector import InvalidSource, ObjectRef, SourceUnavailable


class S3Storage:
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

    async def download_to(self, ref: ObjectRef, path: Path) -> None:
        """Yuklab oladi va checksum’ni tekshiradi (mos kelmasa — doimiy xato)."""
        try:
            await asyncio.to_thread(self._client.download_file, ref.bucket, ref.key, str(path))
        except self._client.exceptions.NoSuchKey as exc:
            raise InvalidSource(f"Fayl topilmadi: {ref.key}") from exc
        except Exception as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                raise InvalidSource(f"Fayl topilmadi: {ref.key}") from exc
            raise SourceUnavailable(f"Ombor mavjud emas: {type(exc).__name__}") from exc
        digest = await asyncio.to_thread(_sha256, path)
        if digest != ref.checksum_sha256:
            raise InvalidSource("Fayl checksum’i mos emas (buzilgan yoki o‘zgartirilgan)")

    async def upload(self, *, bucket: str, key: str, path: Path, content_type: str) -> None:
        try:
            await asyncio.to_thread(self._client.upload_file, str(path), bucket, key,
                                    ExtraArgs={"ContentType": content_type})
        except Exception as exc:
            raise SourceUnavailable(f"Batch’ni yuklab bo‘lmadi: {type(exc).__name__}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
