from datetime import timedelta
from uuid import uuid4

import pytest
from abo_messaging import Outcome
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_runtime.adapters.fake_provider import FakeProvider
from ai_runtime.adapters.hash_embedder import HashEmbedder
from ai_runtime.adapters.http_tools import HttpBusinessTools
from ai_runtime.adapters.s3_store import S3ObjectStore
from ai_runtime.adapters.sql_rows import bind_tenant
from ai_runtime.adapters.sql_store import SqlRunStore
from ai_runtime.bootstrap.container import Container, make_runner
from ai_runtime.bootstrap.settings import Settings
from ai_runtime.ports.store import LeaseLost
from tests.fake_core import CONTRACTS, SERVICE_TOKEN, FakeCore, validate

from .helpers import cancel_envelope, outbox_events, processor, run_agent_envelope

pytestmark = pytest.mark.integration


def make(engine: AsyncEngine, core: FakeCore, owner: str, lease: int = 30):  # type: ignore[no-untyped-def]
    tools = HttpBusinessTools(base_url="http://core", service_token=SERVICE_TOKEN,
                              client=core.client(), backoff_seconds=0)
    container = Container(settings=Settings(lease_seconds=lease), engine=engine, tools=tools,
                          provider=FakeProvider(), embedder=HashEmbedder(),
                          objects=S3ObjectStore(endpoint_url="http://unused", access_key="",
                                                secret_key=""))
    return make_runner(container, owner=owner)


async def status_of(engine: AsyncEngine, tenant_id, step_id) -> str | None:  # type: ignore[no-untyped-def]
    async with engine.connect() as conn, conn.begin():
        await bind_tenant(conn, tenant_id)
        return (await conn.execute(text(
            "SELECT status FROM agent.agent_runs WHERE task_step_id = :s"),
            {"s": step_id})).scalar()


async def test_run_agent_end_to_end(db: AsyncEngine) -> None:
    tenant = uuid4()
    env = run_agent_envelope(tenant, "O‘tgan oy filiallar savdosini solishtir")
    p = processor(db)
    assert await p.process(env.to_json(), attempt=1, max_attempts=3) is Outcome.PROCESSED
    assert await p.process(env.to_json(), attempt=1, max_attempts=3) is Outcome.DUPLICATE
    core = FakeCore()
    assert await make(db, core, "w1").run_once()
    assert await status_of(db, tenant, env.payload["task_step_id"]) == "succeeded"

    events = await outbox_events(db, tenant)
    types = [e["event_type"] for e in events]
    assert types[-1] == "AgentRunCompleted.v1" and "AgentRunProgressed.v1" in types
    for e in events:
        assert e["producer"] == "ai_runtime" and e["causation_id"] == str(env.event_id)
        assert e["correlation_id"] == str(env.correlation_id)
        validate(CONTRACTS / "events" / f"{e['event_type'].replace('.v1', '')}.v1.json",
                 e["payload"])
    async with db.connect() as conn:
        left = (await conn.execute(text("SELECT count(*) FROM agent.run_queue"))).scalar()
    assert left == 0


async def test_runs_are_tenant_isolated(db: AsyncEngine) -> None:
    a, b = uuid4(), uuid4()
    env = run_agent_envelope(a, "savdo")
    await processor(db).process(env.to_json(), attempt=1, max_attempts=3)
    assert await status_of(db, a, env.payload["task_step_id"]) == "queued"
    assert await status_of(db, b, env.payload["task_step_id"]) is None
    async with db.connect() as conn:
        # Tenant kontekstisiz hech narsa ko‘rinmaydi.
        seen = (await conn.execute(text("SELECT count(*) FROM agent.agent_runs"))).scalar()
    assert seen == 0


async def test_cancel_command(db: AsyncEngine) -> None:
    tenant = uuid4()
    env = run_agent_envelope(tenant, "savdo")
    p = processor(db)
    await p.process(env.to_json(), attempt=1, max_attempts=3)
    await p.process(cancel_envelope(env).to_json(), attempt=1, max_attempts=3)
    core = FakeCore()
    await make(db, core, "w1").run_once()
    assert core.calls == []
    assert await status_of(db, tenant, env.payload["task_step_id"]) == "cancelled"
    completed = (await outbox_events(db, tenant))[-1]["payload"]
    assert completed["status"] == "cancelled"


async def test_expired_lease_is_reclaimed_from_checkpoint(db: AsyncEngine) -> None:
    tenant = uuid4()
    env = run_agent_envelope(tenant, "O‘tgan oy filiallar savdosini solishtir")
    await processor(db).process(env.to_json(), attempt=1, max_attempts=3)
    core = FakeCore()
    first = make(db, core, "w1")
    store = first._store
    original = store.commit_step

    async def crash(run, owner, lease, events):  # type: ignore[no-untyped-def]
        await original(run, owner, lease, events)
        if len(run.checkpoint.tool_outputs()) == 2:
            raise RuntimeError("worker yiqildi")

    store.commit_step = crash  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await first.run_once()
    async with db.connect() as conn, conn.begin():
        await conn.execute(text("UPDATE agent.run_queue SET lease_expires_at = now() - "
                                "interval '1 second'"))
    assert await make(db, core, "w2").run_once()
    assert await status_of(db, tenant, env.payload["task_step_id"]) == "succeeded"
    names = core.names()
    assert names.count("list_available_metrics") == 1 and names.count("run_metric_query") == 1


async def test_stale_worker_cannot_commit_after_takeover(db: AsyncEngine) -> None:
    tenant = uuid4()
    env = run_agent_envelope(tenant, "savdo")
    await processor(db).process(env.to_json(), attempt=1, max_attempts=3)
    store = SqlRunStore(db)
    stale = await store.claim("w1", timedelta(seconds=30))
    assert stale is not None
    assert await store.claim("w2", timedelta(seconds=30)) is None  # lease hali amal qiladi
    async with db.connect() as conn, conn.begin():
        await conn.execute(text("UPDATE agent.run_queue SET lease_expires_at = now() - "
                                "interval '1 second'"))
    fresh = await store.claim("w2", timedelta(seconds=30))
    assert fresh is not None and fresh.id == stale.id
    with pytest.raises(LeaseLost):
        await store.commit_step(stale, "w1", timedelta(seconds=30), [])
    await store.commit_step(fresh, "w2", timedelta(seconds=30), [])
