from typing import Protocol


class EmbeddingUnavailable(Exception):
    """Provider javob bermadi yoki xato qaytardi (Business matnli qidiruvga tushadi)."""


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Har matn uchun bitta vektor, bir xil tartibda."""
        ...


class ObjectStore(Protocol):
    async def read_jsonl(self, ref: dict[str, object]) -> list[dict[str, object]]:
        """Checksum tekshiriladi; mos kelmasa ValueError."""
        ...

    async def put_bytes(self, bucket: str, key: str, data: bytes, *,
                        content_type: str) -> dict[str, object]: ...
