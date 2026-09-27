"""Kiruvchi command’lar (payload entrypoint’da tekshirilib shu tiplarga aylantiriladi)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..domain.mapping import SourceMapping
from ..ports.connector import ObjectRef


@dataclass(frozen=True, slots=True)
class DiscoverSchema:
    discovery_id: UUID
    data_source_id: UUID
    connector_id: str
    object_ref: ObjectRef | None
    requested_by: UUID


@dataclass(frozen=True, slots=True)
class ConfigureSource:
    data_source_id: UUID
    connector_id: str
    mapping_version: int
    mapping: SourceMapping
    approved_by: UUID
    approved_at: datetime


@dataclass(frozen=True, slots=True)
class SyncSource:
    sync_run_id: UUID
    data_source_id: UUID
    connector_id: str
    mode: str
    mapping_version: int
    object_ref: ObjectRef | None
    requested_by: UUID
