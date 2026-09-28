from datetime import UTC, datetime, timedelta
from uuid import uuid4

from business.contexts.integrations.domain.freshness import freshness

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def src(status: str, minutes: float) -> dict[str, object]:
    return {"id": uuid4(), "name": "savdo.csv", "status": status,
            "updated_at": NOW - timedelta(minutes=minutes)}


def test_freshness_states() -> None:
    limit = timedelta(minutes=5)
    assert freshness([src("synced", 60)], NOW, limit).state == "fresh"
    assert freshness([src("syncing", 1)], NOW, limit).state == "pending"
    stale = freshness([src("synced", 1), src("discovering", 12)], NOW, limit)
    assert stale.state == "stale" and "12 daqiqadan beri" in (stale.message or "")
    assert "fayl o‘qilishi" in (stale.message or "")
    assert [w["stale"] for w in stale.waiting] == [True]
