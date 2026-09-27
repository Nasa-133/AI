"""Sync Engine: o‘qish → normallashtirish → JSONL → checksum → yuklash.

Connector’lar bu mexanikani qayta yozmaydi (TZ 13.10).
"""

import asyncio
import hashlib
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from ..domain.batch import Rejection, RejectionReport
from ..domain.mapping import RowRejected, SourceMapping, normalize_row
from ..ports.connector import Connector, ObjectRef, SourceHandle
from ..ports.storage import ObjectStorage

HEARTBEAT_EVERY_ROWS = 10_000


class SchemaChanged(Exception):
    """Tasdiqlangan mapping’dagi ustunlar manbada yo‘q."""


@dataclass(frozen=True, slots=True)
class BatchOutput:
    entity: str
    record_count: int
    object_ref: ObjectRef
    rejections: RejectionReport


def canonical_key(tenant_id: UUID, data_source_id: UUID, sync_run_id: UUID, entity: str) -> str:
    return f"canonical/{tenant_id}/{data_source_id}/{sync_run_id}/{entity}.jsonl"


class SyncEngine:
    def __init__(self, storage: ObjectStorage, *, bucket: str,
                 work_dir: Path | None = None) -> None:
        self._storage = storage
        self._bucket = bucket
        self._work_dir = work_dir

    async def run(
        self,
        connector: Connector,
        source: SourceHandle,
        mapping: SourceMapping,
        *,
        sync_run_id: UUID,
        heartbeat: Callable[[], Awaitable[None]] | None = None,
    ) -> BatchOutput:
        rejections = RejectionReport()
        digest = hashlib.sha256()
        count = size = 0
        id_column = next((i.source_column for i in mapping.items
                          if i.canonical_field == "source_id"), None)
        fd, tmp_name = tempfile.mkstemp(suffix=".jsonl", dir=self._work_dir)
        path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as out:
                checked_header = False
                async for row_number, row in connector.read_rows(source, mapping.entity):
                    if not checked_header:
                        missing = [c for c in mapping.source_columns if c not in row]
                        if missing:
                            raise SchemaChanged(f"Manbada ustunlar yo‘q: {', '.join(missing)}")
                        checked_header = True
                    try:
                        record = normalize_row(mapping, row)
                    except RowRejected as exc:
                        source_id = row.get(id_column) if id_column else None
                        rejections.add(Rejection(row_number, (source_id or "").strip() or None,
                                                 exc.reason))
                        continue
                    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                    data = (line + "\n").encode()
                    out.write(data)
                    digest.update(data)
                    size += len(data)
                    count += 1
                    if heartbeat is not None and count % HEARTBEAT_EVERY_ROWS == 0:
                        await heartbeat()
            key = canonical_key(source.tenant_id, source.data_source_id, sync_run_id,
                                mapping.entity)
            await self._storage.upload(bucket=self._bucket, key=key, path=path,
                                       content_type="application/x-ndjson")
        finally:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        ref = ObjectRef(self._bucket, key, digest.hexdigest(), size)
        return BatchOutput(mapping.entity, count, ref, rejections)
