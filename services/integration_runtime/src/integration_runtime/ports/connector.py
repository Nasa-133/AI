"""Connector SDK (TZ 13.10). Connector faqat manbani o‘qiydi; normallashtirish, batch,
checksum, rad etish va idempotentlik — Sync Engine’ning ishi (application)."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from ..domain.mapping import SourceConfig


@dataclass(frozen=True, slots=True)
class ObjectRef:
    bucket: str
    key: str
    checksum_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ConnectorManifest:
    connector_id: str
    version: str
    display_name: str
    supported_entities: tuple[str, ...]
    capabilities: tuple[str, ...]
    is_demo: bool
    requires_object_ref: bool


@dataclass(frozen=True, slots=True)
class SourceHandle:
    tenant_id: UUID
    data_source_id: UUID
    object_ref: ObjectRef | None
    config: SourceConfig


@dataclass(frozen=True, slots=True)
class DiscoveredSource:
    source_name: str
    columns: list[str]
    sample_rows: list[list[str | None]]


class SourceUnavailable(Exception):
    """Manba vaqtincha mavjud emas — qayta urinish mumkin."""


class InvalidSource(Exception):
    """Manba o‘qib bo‘lmaydi (buzilgan fayl, checksum mos emas) — qayta urinish foydasiz."""


RawRow = dict[str, str | None]


class Connector(Protocol):
    @property
    def manifest(self) -> ConnectorManifest: ...

    async def discover_schema(self, source: SourceHandle) -> list[DiscoveredSource]: ...

    def read_rows(self, source: SourceHandle, entity: str) -> AsyncIterator[tuple[int, RawRow]]:
        """(satr raqami — manbadagi fizik satr, sarlavha 1-satr; xom qiymatlar)."""
        ...
