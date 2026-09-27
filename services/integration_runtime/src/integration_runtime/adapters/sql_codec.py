"""Domain obyektlari ↔ JSONB ustunlar."""

from typing import Any

from ..domain.mapping import MappingItem, SourceConfig, SourceMapping, Transform
from ..ports.connector import ObjectRef


def mapping_to_json(m: SourceMapping) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = {"delimiter": m.config.delimiter, "encoding": m.config.encoding,
              "status_map": dict(m.config.status_map)}
    items = [{"canonical_field": i.canonical_field, "source_column": i.source_column,
              "transform": i.transform.value, "constant": i.constant} for i in m.items]
    return config, items


def mapping_from_json(entity: str, config: dict[str, Any],
                      items: list[dict[str, Any]]) -> SourceMapping:
    return SourceMapping(
        entity=entity,
        items=tuple(MappingItem(i["canonical_field"], i["source_column"],
                                Transform(i["transform"]), i["constant"]) for i in items),
        config=SourceConfig(delimiter=config["delimiter"], encoding=config["encoding"],
                            status_map=dict(config["status_map"])),
    )


def ref_to_json(ref: ObjectRef | None) -> dict[str, Any] | None:
    if ref is None:
        return None
    return {"bucket": ref.bucket, "key": ref.key, "checksum_sha256": ref.checksum_sha256,
            "size_bytes": ref.size_bytes}


def ref_from_json(data: dict[str, Any] | None) -> ObjectRef | None:
    if data is None:
        return None
    return ObjectRef(data["bucket"], data["key"], data["checksum_sha256"], int(data["size_bytes"]))
