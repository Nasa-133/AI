from uuid import uuid4

import pytest

from abo_messaging import Envelope, InvalidEnvelope, new_envelope


def make() -> Envelope:
    return new_envelope(event_type="SourceBatchReady.v1", producer="integration_runtime",
                        tenant_id=uuid4(), aggregate_id=uuid4(), aggregate_version=2,
                        payload={"batch_id": "b1", "amount": "12.50"})


def test_roundtrip_preserves_all_fields() -> None:
    env = make()
    assert Envelope.from_json(env.to_json()) == env
    assert env.correlation_id == env.event_id and env.major_version == 1


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(event_type="source_batch_ready"),
    lambda d: d.update(producer="browser"),
    lambda d: d.update(payload=[1]),
    lambda d: d.update(occurred_at="2026-09-27T10:00:00"),
    lambda d: d.pop("tenant_id"),
    lambda d: d.update(event_id="not-a-uuid"),
])
def test_invalid_envelopes_are_rejected(mutate) -> None:  # type: ignore[no-untyped-def]
    import json
    data = json.loads(make().to_json())
    mutate(data)
    with pytest.raises(InvalidEnvelope):
        Envelope.from_json(json.dumps(data).encode())


def test_garbage_is_invalid() -> None:
    with pytest.raises(InvalidEnvelope):
        Envelope.from_json(b"\xff not json")
