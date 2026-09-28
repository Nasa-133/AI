"""Broker handler’lari (navbat `ai_runtime.agent`): envelope → application command."""

from datetime import datetime
from uuid import UUID

from abo_messaging import Envelope, Handler, PermanentError, enqueue, new_envelope
from sqlalchemy.ext.asyncio import AsyncConnection

from ..application.commands import RunAgentCommand, accept_run, cancel_run
from ..application.embeddings import EmbeddingRequest, generate_embeddings
from ..ports.embeddings import EmbeddingProvider, ObjectStore
from .sql_commands import SqlRunCommands
from .sql_rows import bind_tenant

QUEUE = "ai_runtime.agent"
EMBEDDINGS_QUEUE = "ai_runtime.embeddings"


async def bind_envelope_tenant(conn: AsyncConnection, envelope: Envelope) -> None:
    await bind_tenant(conn, envelope.tenant_id)


def make_handlers(*, max_tool_calls: int) -> dict[str, Handler]:
    async def run_agent(conn: AsyncConnection, envelope: Envelope) -> None:
        p = envelope.payload
        try:
            cmd = RunAgentCommand(
                tenant_id=envelope.tenant_id,
                task_id=UUID(p["task_id"]),
                task_step_id=UUID(p["task_step_id"]),
                role_key=str(p["agent_role_key"]),
                instruction=str(p["sanitized_instruction"]),
                locale=str(p["locale"]),
                deadline=datetime.fromisoformat(p["deadline"]),
                capability_token=str(p["capability_token"]),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.event_id,
                context_refs=tuple(dict(r) for r in p.get("context_refs") or ()),
                conversation=tuple(
                    {"role": str(t["role"]), "agent_role_key": t.get("agent_role_key"),
                     "text": str(t["text"])} for t in p.get("conversation") or ()),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise PermanentError(f"RunAgent payload noto‘g‘ri: {exc}") from exc
        await accept_run(SqlRunCommands(conn), cmd, max_tool_calls=max_tool_calls)

    async def cancel_agent_run(conn: AsyncConnection, envelope: Envelope) -> None:
        try:
            step = UUID(envelope.payload["task_step_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise PermanentError(f"CancelAgentRun payload noto‘g‘ri: {exc}") from exc
        await cancel_run(SqlRunCommands(conn), step)

    return {"RunAgent.v1": run_agent, "CancelAgentRun.v1": cancel_agent_run}


def make_embedding_handlers(*, store: ObjectStore, provider: EmbeddingProvider,
                            bucket: str) -> dict[str, Handler]:
    """Natija eventi inbox tranzaksiyasida outbox’ga yoziladi (dedup bilan atomar)."""

    async def generate(conn: AsyncConnection, envelope: Envelope) -> None:
        p = envelope.payload
        try:
            req = EmbeddingRequest(
                tenant_id=envelope.tenant_id, request_id=UUID(p["request_id"]),
                document_version_id=UUID(p["document_version_id"]),
                chunks_ref=dict(p["chunks_ref"]), chunk_count=int(p["chunk_count"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise PermanentError(f"GenerateEmbeddings payload noto‘g‘ri: {exc}") from exc
        result = await generate_embeddings(req, store=store, provider=provider, bucket=bucket)
        await enqueue(conn, new_envelope(
            event_type="EmbeddingsGenerated.v1", producer="ai_runtime",
            tenant_id=envelope.tenant_id, aggregate_id=req.document_version_id,
            aggregate_version=1, payload=result, correlation_id=envelope.correlation_id,
            causation_id=envelope.event_id))

    return {"GenerateEmbeddings.v1": generate}
