from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from business.kernel.errors import BusinessError

from ..domain.access import Access
from ..domain.structure import Chunk, Section


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: UUID
    title: str
    current_version_id: UUID | None
    visibility: str
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    shared_with: frozenset[UUID] = frozenset()

    @property
    def access(self) -> Access:
        return Access(self.created_by, self.visibility, self.shared_with)


@dataclass(frozen=True, slots=True)
class VersionRecord:
    id: UUID
    document_id: UUID
    version_no: int
    kind: str
    base_version_id: UUID | None
    filename: str
    content_type: str
    bucket: str
    object_key: str
    sha256: str
    size_bytes: int
    parse_status: str
    parse_error: str | None
    quality: dict[str, Any]
    embedding_status: str
    comment: str | None
    created_by: UUID
    created_at: datetime | None = None  # yangi yozuvda DB qo‘yadi

    @property
    def fmt(self) -> str:
        return self.filename.rsplit(".", 1)[-1].lower()

    def object_ref(self) -> dict[str, Any]:
        return {"bucket": self.bucket, "key": self.object_key,
                "checksum_sha256": self.sha256.strip(), "size_bytes": self.size_bytes}


@dataclass(frozen=True, slots=True)
class SearchHit:
    document_id: UUID
    document_title: str
    version_id: UUID
    version_no: int
    chunk_id: UUID
    section_ids: list[str]
    locator: str
    text: str
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class SearchScope:
    """Foydalanuvchi ko‘ra oladigan hujjatlarning joriy versiyalari (ACL qidiruvdan oldin)."""

    version_ids: list[UUID] = field(default_factory=list)


class DocumentStore(Protocol):
    async def create_document(self, document_id: UUID, title: str, user_id: UUID) -> None: ...
    async def add_version(self, v: VersionRecord) -> None: ...
    async def set_current(self, document_id: UUID, version_id: UUID) -> None: ...
    async def get(self, document_id: UUID) -> DocumentRecord | None: ...
    async def list_visible(self, *, user_id: UUID, see_all: bool, query: str | None,
                           limit: int) -> list[DocumentRecord]: ...
    async def get_version(self, version_id: UUID) -> VersionRecord | None: ...
    async def versions(self, document_id: UUID) -> list[VersionRecord]: ...
    async def next_version_no(self, document_id: UUID) -> int: ...
    async def set_parse(self, version_id: UUID, status: str, error: str | None,
                        quality: dict[str, Any]) -> None: ...
    async def set_embedding_status(self, version_id: UUID, status: str) -> None: ...
    async def save_sections(self, version_id: UUID, sections: list[Section]) -> None: ...
    async def sections(self, version_id: UUID) -> list[Section]: ...
    async def save_chunks(self, document_id: UUID, version_id: UUID,
                          chunks: list[Chunk]) -> list[tuple[UUID, str]]: ...
    async def chunks_of(self, version_id: UUID) -> list[tuple[UUID, str]]: ...
    async def set_embeddings(self, version_id: UUID, vectors: dict[UUID, list[float]],
                             model: str) -> int: ...
    async def search_scope(self, *, user_id: UUID, see_all: bool,
                           document_ids: list[UUID] | None) -> SearchScope: ...
    async def search_text(self, scope: SearchScope, terms: list[str],
                          limit: int) -> list[SearchHit]: ...
    async def search_vector(self, scope: SearchScope, vector: list[float],
                            limit: int) -> list[SearchHit]: ...
    async def mark_deleting(self, document_id: UUID) -> UUID: ...
    async def finish_cleanup(self, document_id: UUID, job_id: UUID, error: str | None) -> None: ...
    async def set_access(self, document_id: UUID, visibility: str,
                         shared_with: frozenset[UUID], *, user_id: UUID) -> None: ...
    async def retryable_cleanups(self, max_attempts: int) -> list[tuple[UUID, UUID, int]]: ...
    async def stale_drafts(self, days: int) -> list[VersionRecord]: ...
    async def delete_version(self, version_id: UUID) -> None: ...


class FileStore(Protocol):
    async def put_file(self, key: str, path: Path, *, content_type: str) -> dict[str, Any]: ...
    async def download(self, ref: dict[str, Any], path: Path) -> None: ...
    async def read_jsonl(self, ref: dict[str, Any]) -> list[dict[str, Any]]: ...
    async def delete(self, bucket: str, key: str) -> None: ...


class Outbox(Protocol):
    async def publish(self, event_type: str, payload: dict[str, Any], *, aggregate_id: UUID,
                      aggregate_version: int) -> None: ...


class DocumentUnreadable(BusinessError):
    """Faylni o‘qib bo‘lmaydi (parol, buzilgan, xavfli tuzilma, timeout); sababi ko‘rsatiladi."""

    code = "DOCUMENT_UNREADABLE"


class Parser(Protocol):
    """Format aniqlash, tuzilma skaneri va izolyatsiyalangan parse. Xatolar — DocumentUnreadable."""

    def detect_format(self, filename: str) -> str: ...
    def scan(self, path: Path, fmt: str) -> None: ...
    async def parse(self, fmt: str, path: Path) -> dict[str, Any]: ...


class QueryEmbedder(Protocol):
    async def embed(self, text: str) -> list[float] | None:
        """Sinxron (≤2 s). Xato yoki AI uzilishida None — qidiruv matnli rejimga tushadi."""
        ...
