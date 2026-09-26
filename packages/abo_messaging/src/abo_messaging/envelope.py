"""Event/command envelope v1 (contracts/events/envelope.v1.json)."""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

Producer = Literal["business", "ai_runtime", "integration_runtime"]
_EVENT_TYPE_RE = re.compile(r"^[A-Z][A-Za-z]+\.v[0-9]+$")
_PRODUCERS = {"business", "ai_runtime", "integration_runtime"}


class InvalidEnvelope(ValueError):
    """Qayta urinish bilan tuzalmaydigan xato: xabar DLQ’ga yuboriladi."""


@dataclass(frozen=True, slots=True)
class Envelope:
    event_id: UUID
    event_type: str
    schema_version: int
    producer: Producer
    occurred_at: datetime
    tenant_id: UUID
    correlation_id: UUID
    causation_id: UUID | None
    traceparent: str | None
    aggregate_id: UUID
    aggregate_version: int
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def major_version(self) -> int:
        return int(self.event_type.rsplit(".v", 1)[1])

    def to_json(self) -> bytes:
        data = asdict(self)
        for key in ("event_id", "tenant_id", "correlation_id", "causation_id", "aggregate_id"):
            data[key] = str(data[key]) if data[key] is not None else None
        data["occurred_at"] = self.occurred_at.isoformat()
        return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()

    @classmethod
    def from_json(cls, raw: bytes) -> "Envelope":
        try:
            data = json.loads(raw)
            if not _EVENT_TYPE_RE.fullmatch(data["event_type"]):
                raise InvalidEnvelope(f"event_type noto‘g‘ri: {data['event_type']!r}")
            if data["producer"] not in _PRODUCERS:
                raise InvalidEnvelope(f"producer noto‘g‘ri: {data['producer']!r}")
            if not isinstance(data["payload"], dict):
                raise InvalidEnvelope("payload obyekt bo‘lishi kerak")
            occurred_at = datetime.fromisoformat(data["occurred_at"])
            if occurred_at.tzinfo is None:
                raise InvalidEnvelope("occurred_at vaqt mintaqasisiz")
            return cls(
                event_id=UUID(data["event_id"]),
                event_type=data["event_type"],
                schema_version=int(data["schema_version"]),
                producer=data["producer"],
                occurred_at=occurred_at,
                tenant_id=UUID(data["tenant_id"]),
                correlation_id=UUID(data["correlation_id"]),
                causation_id=UUID(data["causation_id"]) if data["causation_id"] else None,
                traceparent=data["traceparent"],
                aggregate_id=UUID(data["aggregate_id"]),
                aggregate_version=int(data["aggregate_version"]),
                payload=data["payload"],
            )
        except InvalidEnvelope:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvalidEnvelope(f"Envelope o‘qilmadi: {exc}") from exc


def new_envelope(
    *,
    event_type: str,
    producer: Producer,
    tenant_id: UUID,
    aggregate_id: UUID,
    aggregate_version: int,
    payload: dict[str, Any],
    correlation_id: UUID | None = None,
    causation_id: UUID | None = None,
    traceparent: str | None = None,
    schema_version: int = 1,
) -> Envelope:
    if not _EVENT_TYPE_RE.fullmatch(event_type):
        raise InvalidEnvelope(f"event_type noto‘g‘ri: {event_type!r}")
    event_id = uuid4()
    return Envelope(
        event_id=event_id,
        event_type=event_type,
        schema_version=schema_version,
        producer=producer,
        occurred_at=datetime.now(UTC),
        tenant_id=tenant_id,
        correlation_id=correlation_id or event_id,
        causation_id=causation_id,
        traceparent=traceparent,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        payload=payload,
    )
