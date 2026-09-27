import copy
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from abo_messaging import Envelope, InboxProcessor, new_envelope
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_runtime.adapters.handlers import QUEUE, bind_envelope_tenant, make_handlers
from tests.fake_core import CONTRACTS, load


def run_agent_envelope(tenant_id: UUID, instruction: str) -> Envelope:
    payload: dict[str, Any] = copy.deepcopy(
        load(CONTRACTS / "commands/fixtures/RunAgent.v1.valid.json"))
    payload.update(task_id=str(uuid4()), task_step_id=str(uuid4()),
                   sanitized_instruction=instruction,
                   deadline=(datetime.now(UTC) + timedelta(minutes=10)).isoformat())
    return new_envelope(event_type="RunAgent.v1", producer="business", tenant_id=tenant_id,
                        aggregate_id=UUID(payload["task_id"]), aggregate_version=1,
                        payload=payload)


def cancel_envelope(run_env: Envelope) -> Envelope:
    return new_envelope(event_type="CancelAgentRun.v1", producer="business",
                        tenant_id=run_env.tenant_id, aggregate_id=run_env.aggregate_id,
                        aggregate_version=2, correlation_id=run_env.correlation_id,
                        payload={"task_id": run_env.payload["task_id"],
                                 "task_step_id": run_env.payload["task_step_id"],
                                 "requested_by": str(uuid4()), "reason": None})


def processor(engine: AsyncEngine) -> InboxProcessor:
    return InboxProcessor(engine, consumer=QUEUE, handlers=make_handlers(max_tool_calls=20),
                          on_transaction_start=bind_envelope_tenant)


async def outbox_events(engine: AsyncEngine, tenant_id: UUID) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT envelope FROM messaging.outbox WHERE tenant_id = :t ORDER BY id"),
            {"t": tenant_id})).scalars().all()
    return [r if isinstance(r, dict) else json.loads(r) for r in rows]
