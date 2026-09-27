"""Dataset, snapshot va to‘liq snapshot’ni versiyali qo‘llash (COPY → staging → close/insert)."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.ingestion import Entity, Quarantined
from ..ports.store import BatchMeta, DatasetRef, SnapshotRef
from .canonical import local_date, to_db_row
from .sql_tables import COLUMNS, TABLES


def snapshot_from_row(r: Any) -> SnapshotRef:
    return SnapshotRef(r.id, r.dataset_id, Entity(r.entity), r.seq, r.as_of, r.row_count,
                       r.quarantined_count)


SNAPSHOT_SELECT = (
    "SELECT s.id, s.dataset_id, d.entity, s.seq, s.as_of, s.row_count, s.quarantined_count"
    " FROM analytics.snapshots s JOIN analytics.datasets d"
    " ON d.tenant_id = s.tenant_id AND d.id = s.dataset_id"
)


class SqlIngestion:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._c = conn
        self._tenant = tenant_id

    async def dataset_for(self, data_source_id: UUID, entity: Entity) -> DatasetRef:
        """Yo‘q bo‘lsa yaratadi; entity uchun faol dataset yo‘q bo‘lsa — shu faol bo‘ladi."""
        now = datetime.now(UTC)
        await self._c.execute(text(
            "INSERT INTO analytics.datasets (tenant_id, id, data_source_id, entity, is_active,"
            " created_at, updated_at) SELECT :t, :id, :ds, :e, NOT EXISTS (SELECT 1 FROM"
            " analytics.datasets WHERE entity = :e AND is_active), :now, :now"
            " ON CONFLICT (tenant_id, data_source_id, entity) DO NOTHING"),
            {"t": self._tenant, "id": uuid4(), "ds": data_source_id, "e": entity.value,
             "now": now})
        r = (await self._c.execute(text(
            "SELECT id, data_source_id, entity, latest_seq FROM analytics.datasets"
            " WHERE data_source_id = :ds AND entity = :e FOR UPDATE"),
            {"ds": data_source_id, "e": entity.value})).one()
        return DatasetRef(r.id, r.data_source_id, Entity(r.entity), r.latest_seq)

    async def snapshot_for_batch(self, dataset_id: UUID, batch_id: UUID) -> SnapshotRef | None:
        r = (await self._c.execute(text(
            SNAPSHOT_SELECT + " WHERE s.dataset_id = :d AND s.batch_id = :b"),
            {"d": dataset_id, "b": batch_id})).first()
        return None if r is None else snapshot_from_row(r)

    async def apply_full_snapshot(self, dataset: DatasetRef, records: list[dict[str, Any]],
                                  quarantined: list[Quarantined], meta: BatchMeta,
                                  timezone: str) -> SnapshotRef:
        entity, table, cols = dataset.entity, TABLES[dataset.entity], COLUMNS[dataset.entity]
        rows = [to_db_row(entity, r, None if entity is Entity.FINANCE_RECEIVABLE
                          else local_date(r["occurred_at"], timezone)) for r in records]
        seq = dataset.latest_seq + 1
        params = {"ds": dataset.id, "seq": seq}
        # Bir tranzaksiyada bir nechta batch bo‘lishi mumkin — har chaqiriqqa alohida nom.
        staging = f"staging_{uuid4().hex}"
        await self._c.execute(text(
            f"CREATE TEMP TABLE {staging} ON COMMIT DROP AS SELECT * FROM {table} WITH NO DATA"))
        raw = await self._c.get_raw_connection()
        await raw.driver_connection.copy_records_to_table(  # type: ignore[union-attr]
            staging,
            records=[(self._tenant, dataset.id, seq, *[r[c] for c in cols]) for r in rows],
            columns=["tenant_id", "dataset_id", "valid_from_seq", *cols],
        )
        # Yo‘qolgan yoki o‘zgargan ochiq satrlar yopiladi; o‘zgarmaganlari tegilmaydi.
        closed = await self._c.execute(text(
            f"UPDATE {table} t SET valid_to_seq = :seq WHERE t.dataset_id = :ds"
            f" AND t.valid_to_seq IS NULL AND NOT EXISTS (SELECT 1 FROM {staging} s"
            " WHERE s.source_id = t.source_id AND s.row_hash = t.row_hash)"), params)
        inserted = await self._c.execute(text(
            f"INSERT INTO {table} SELECT s.* FROM {staging} s WHERE NOT EXISTS (SELECT 1 FROM"
            f" {table} t WHERE t.dataset_id = :ds AND t.valid_to_seq IS NULL"
            " AND t.source_id = s.source_id AND t.row_hash = s.row_hash)"), params)
        await self._c.execute(text(f"DROP TABLE {staging}"))
        row_count: int = (await self._c.execute(text(
            f"SELECT count(*) FROM {table} WHERE dataset_id = :ds AND valid_to_seq IS NULL"),
            params)).scalar_one()

        snapshot_id, now = uuid4(), datetime.now(UTC)
        await self._c.execute(text(
            "INSERT INTO analytics.snapshots (tenant_id, id, dataset_id, seq, batch_id,"
            " sync_run_id, as_of, row_count, inserted_count, closed_count, quarantined_count,"
            " created_at) VALUES (:t, :id, :ds, :seq, :b, :run, :as_of, :rows, :ins, :cl, :q,"
            " :now)"),
            {"t": self._tenant, "id": snapshot_id, "ds": dataset.id, "seq": seq,
             "b": meta.batch_id, "run": meta.sync_run_id, "as_of": meta.extracted_at,
             "rows": row_count, "ins": inserted.rowcount, "cl": closed.rowcount,
             "q": len(quarantined), "now": now})
        await self._c.execute(text(
            "UPDATE analytics.datasets SET latest_seq = :seq, latest_snapshot_id = :sid,"
            " updated_at = :now WHERE id = :ds"),
            {"seq": seq, "sid": snapshot_id, "now": now, "ds": dataset.id})
        if quarantined:
            await self._c.execute(text(
                "INSERT INTO analytics.quarantine (tenant_id, id, dataset_id, snapshot_id,"
                " source_id, reason, record, created_at) VALUES (:t, :id, :ds, :sid, :src, :r,"
                " CAST(:rec AS jsonb), :now)"),
                [{"t": self._tenant, "id": uuid4(), "ds": dataset.id, "sid": snapshot_id,
                  "src": q.record.get("source_id"), "r": q.reason,
                  "rec": json.dumps({k: v for k, v in q.record.items() if not k.startswith("_")},
                                    default=str, ensure_ascii=False), "now": now}
                 for q in quarantined])
        return SnapshotRef(snapshot_id, dataset.id, entity, seq, meta.extracted_at, row_count,
                           len(quarantined))
