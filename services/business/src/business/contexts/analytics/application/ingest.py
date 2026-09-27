"""SourceBatchReady → karantin → versiyali snapshot → DatasetSnapshotPublished (TZ 16)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from ..domain.ingestion import Entity, screen
from ..ports.store import (
    AnalyticsStore,
    BatchMeta,
    CanonicalBatchReader,
    EventOutbox,
    SnapshotRef,
)


@dataclass(frozen=True, slots=True)
class BatchReady:
    batch_id: UUID
    sync_run_id: UUID
    data_source_id: UUID
    entity: Entity
    object_ref: dict[str, Any]
    extracted_at: datetime
    is_full_snapshot: bool

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> "BatchReady":
        return cls(UUID(p["batch_id"]), UUID(p["sync_run_id"]), UUID(p["data_source_id"]),
                   Entity(p["entity"]), p["object_ref"],
                   datetime.fromisoformat(p["extracted_at"]), bool(p["is_full_snapshot"]))


class IncrementalNotSupported(Exception):
    """P0 connector’lari faqat to‘liq snapshot beradi; inkremental — P1."""


async def ingest_batch(store: AnalyticsStore, reader: CanonicalBatchReader, outbox: EventOutbox,
                       batch: BatchReady, *, timezone: str) -> SnapshotRef:
    if not batch.is_full_snapshot:
        raise IncrementalNotSupported("Inkremental batch hali qo‘llanmaydi (P1).")
    dataset = await store.dataset_for(batch.data_source_id, batch.entity)
    existing = await store.snapshot_for_batch(dataset.id, batch.batch_id)
    if existing is not None:
        return existing  # takroriy yetkazish: ikkinchi snapshot yaratilmaydi
    records = await reader.read(batch.object_ref, batch.entity)
    screened = screen(batch.entity, records)
    snapshot = await store.apply_full_snapshot(
        dataset, screened.accepted, screened.quarantined,
        BatchMeta(batch.batch_id, batch.sync_run_id, batch.extracted_at), timezone,
    )
    await outbox.publish(
        "DatasetSnapshotPublished.v1",
        {
            "snapshot_id": str(snapshot.id),
            "dataset_id": str(dataset.id),
            "entities": [batch.entity.value],
            "as_of": snapshot.as_of.isoformat(),
            "row_counts": {batch.entity.value: snapshot.row_count},
            "quarantined_count": snapshot.quarantined_count,
            "source_batch_ids": [str(batch.batch_id)],
        },
        aggregate_id=dataset.id,
        aggregate_version=snapshot.seq,
    )
    return snapshot
