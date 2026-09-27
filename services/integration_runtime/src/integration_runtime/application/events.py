"""Chiquvchi event payload’lari (contracts/events/*.v1.json shakliga aynan mos)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from ..domain.batch import RejectionReport
from ..domain.mapping import MappingItem
from ..domain.templates import Suggestion
from ..ports.connector import DiscoveredSource, ObjectRef
from ..ports.repository import BatchRecord, SyncRun

MAX_DISCOVERED_ENTITIES = 20


def _ts(value: datetime) -> str:
    return value.isoformat()


def object_ref_payload(ref: ObjectRef) -> dict[str, Any]:
    return {"bucket": ref.bucket, "key": ref.key, "checksum_sha256": ref.checksum_sha256,
            "size_bytes": ref.size_bytes}


def mapping_payload(items: tuple[MappingItem, ...]) -> list[dict[str, Any]]:
    return [{"canonical_field": i.canonical_field, "source_column": i.source_column,
             "transform": i.transform.value, "constant": i.constant} for i in items]


def schema_discovered(
    *,
    discovery_id: UUID,
    data_source_id: UUID,
    connector_id: str,
    found: list[tuple[DiscoveredSource, Suggestion]],
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    entities = [
        {
            "entity": suggestion.entity,
            "source_name": source.source_name[:300],
            "match_score": suggestion.match_score,
            "columns": [c[:200] for c in source.columns[:500]],
            "sample_rows": [[None if v is None else v[:1000] for v in row]
                            for row in source.sample_rows[:5]],
            "suggested_mapping": mapping_payload(suggestion.mapping),
            "unmapped_required_fields": list(suggestion.unmapped_required_fields),
        }
        for source, suggestion in found[:MAX_DISCOVERED_ENTITIES]
    ]
    return {
        "discovery_id": str(discovery_id),
        "data_source_id": str(data_source_id),
        "connector_id": connector_id,
        "entities": entities,
        "error_code": error_code,
        "error_message": error_message[:1000] if error_message else None,
    }


def source_configured(data_source_id: UUID, mapping_version: int, *, accepted: bool,
                      error_message: str | None = None) -> dict[str, Any]:
    return {"data_source_id": str(data_source_id), "mapping_version": mapping_version,
            "accepted": accepted, "error_message": error_message[:1000] if error_message else None}


def source_batch_ready(batch: BatchRecord) -> dict[str, Any]:
    return {
        "batch_id": str(batch.id),
        "data_source_id": str(batch.data_source_id),
        "sync_run_id": str(batch.sync_run_id),
        "connector_id": batch.connector_id,
        "connector_version": batch.connector_version,
        "entity": batch.entity,
        "canonical_schema_version": batch.canonical_schema_version,
        "record_count": batch.record_count,
        "object_ref": object_ref_payload(batch.object_ref),
        "checksum_sha256": batch.object_ref.checksum_sha256,
        "extracted_at": _ts(batch.extracted_at),
        "window": None,
        "is_full_snapshot": batch.is_full_snapshot,
    }


def sync_run_completed(run: SyncRun, batch: BatchRecord, rejections: RejectionReport,
                       finished_at: datetime) -> dict[str, Any]:
    return {
        "sync_run_id": str(run.id),
        "data_source_id": str(run.data_source_id),
        "status": "partial" if rejections.count else "succeeded",
        "mapping_version": run.mapping_version,
        "batch_ids": [str(batch.id)],
        "record_counts": [{"entity": batch.entity, "count": batch.record_count}],
        "rejected_count": rejections.count,
        "rejection_samples": [
            {"row_number": r.row_number,
             "source_id": r.source_id[:300] if r.source_id else None,
             "reason": r.reason[:500]}
            for r in rejections.samples
        ],
        "finished_at": _ts(finished_at),
    }


def sync_run_failed(run: SyncRun, *, error_code: str, message: str, retryable: bool,
                    batches_published: int = 0) -> dict[str, Any]:
    return {
        "sync_run_id": str(run.id),
        "data_source_id": str(run.data_source_id),
        "connector_id": run.connector_id,
        "error_code": error_code,
        "retryable": retryable,
        "message": message[:500] or error_code,
        "batches_published": batches_published,
    }
