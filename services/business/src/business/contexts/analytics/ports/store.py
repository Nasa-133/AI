from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from ..domain.ingestion import Entity, Quarantined
from ..domain.metrics import Component, Dimension
from ..domain.query import Period, QuerySpec


@dataclass(frozen=True, slots=True)
class DatasetRef:
    id: UUID
    data_source_id: UUID
    entity: Entity
    latest_seq: int


@dataclass(frozen=True, slots=True)
class SnapshotRef:
    id: UUID
    dataset_id: UUID
    entity: Entity
    seq: int
    as_of: datetime
    row_count: int
    quarantined_count: int


# Bir obyektning faol snapshot’lari — har manba (dataset) uchun bittadan; qo‘shib hisoblanadi.
SnapshotSet = tuple[SnapshotRef, ...]
Snapshots = dict[Entity, SnapshotSet]


def snapshot_list(snapshots: "Snapshots") -> list[SnapshotRef]:
    return [s for parts in snapshots.values() for s in parts]


@dataclass(frozen=True, slots=True)
class BatchMeta:
    batch_id: UUID
    sync_run_id: UUID
    extracted_at: datetime


@dataclass(frozen=True, slots=True)
class ComponentRow:
    """Bitta guruh: o‘lcham qiymatlari (spec tartibida, oxirida valyuta) va yig‘indilar."""

    key: tuple[str, ...]
    values: dict[Component, Decimal]


@dataclass(frozen=True, slots=True)
class MetricSettings:
    version: int
    settings: dict[str, Any]
    approved_by: UUID
    approved_at: datetime


@dataclass(frozen=True, slots=True)
class StoredQuery:
    id: UUID
    kind: str
    spec: dict[str, Any]
    snapshot_ids: list[UUID]
    result: dict[str, Any]
    created_by: UUID
    task_id: UUID | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Coverage:
    first_day: date | None
    last_day: date | None
    currencies: list[str] = field(default_factory=list)


class AnalyticsStore(Protocol):
    """Joriy tranzaksiya va tenant kontekstiga bog‘langan saqlash porti."""

    async def dataset_for(self, data_source_id: UUID, entity: Entity) -> DatasetRef: ...
    async def snapshot_for_batch(self, dataset_id: UUID, batch_id: UUID) -> SnapshotRef | None: ...

    async def apply_full_snapshot(
        self,
        dataset: DatasetRef,
        records: list[dict[str, Any]],
        quarantined: list[Quarantined],
        meta: BatchMeta,
        timezone: str,
    ) -> SnapshotRef:
        """Canonical record’lar (kontrakt ko‘rinishida) → versiyali satrlar; sana — tenant TZ’da."""
        ...

    async def active_snapshots(self) -> Snapshots: ...
    async def snapshots_by_ids(self, ids: list[UUID]) -> Snapshots: ...

    async def sales_components(
        self, spec: QuerySpec, period: Period, snapshots: Snapshots,
        dimensions: tuple[Dimension, ...],
    ) -> list[ComponentRow]: ...

    async def receivable_components(
        self, spec: QuerySpec, as_of: date, snapshot: SnapshotSet,
        dimensions: tuple[Dimension, ...],
    ) -> list[ComponentRow]: ...

    async def crm_components(
        self, spec: QuerySpec, period: Period, snapshot: SnapshotSet,
        dimensions: tuple[Dimension, ...],
    ) -> list[ComponentRow]: ...

    async def dimension_names(
        self, dimension: Dimension, codes: list[str], snapshots: Snapshots
    ) -> dict[str, str]: ...

    async def coverage(self, snapshots: Snapshots) -> Coverage: ...

    async def metric_settings(self) -> MetricSettings | None: ...
    async def save_metric_settings(self, settings: MetricSettings) -> None: ...

    async def save_query(self, query: StoredQuery) -> None: ...
    async def get_query(self, query_id: UUID) -> StoredQuery | None: ...


class CanonicalBatchReader(Protocol):
    async def read(self, object_ref: dict[str, Any], entity: Entity) -> list[dict[str, Any]]:
        """Batch faylini o‘qiydi, checksum va kontraktni tekshiradi (buzilgan — doimiy xato)."""
        ...


class EventOutbox(Protocol):
    async def publish(self, event_type: str, payload: dict[str, Any], *, aggregate_id: UUID,
                      aggregate_version: int) -> None: ...
