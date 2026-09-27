"""Broker xabarlari → application command’lari (navbat `integration_runtime.sync`)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from abo_messaging import Envelope, PermanentError
from sqlalchemy.ext.asyncio import AsyncConnection

from ..adapters.sql_codec import ref_from_json
from ..adapters.sql_uow import ConnectionScope, bind_tenant
from ..application.commands import ConfigureSource, DiscoverSchema, SyncSource
from ..application.handlers import CommandHandlers
from ..domain.mapping import MappingItem, SourceConfig, SourceMapping, Transform
from ..ports.repository import MessageContext

QUEUE = "integration_runtime.sync"


def _ctx(env: Envelope) -> MessageContext:
    return MessageContext(env.tenant_id, env.correlation_id, env.event_id, env.traceparent)


def _mapping(p: dict[str, Any]) -> SourceMapping:
    cfg = p["config"]
    return SourceMapping(
        entity=p["entity"],
        items=tuple(MappingItem(i["canonical_field"], i["source_column"],
                                Transform(i["transform"]), i["constant"]) for i in p["mapping"]),
        config=SourceConfig(
            delimiter=cfg["delimiter"] or ",", encoding=cfg["encoding"] or "utf-8",
            status_map={m["source_value"]: m["canonical_value"] for m in cfg["status_map"]},
        ),
    )


class MessageHandlers:
    def __init__(self, handlers: CommandHandlers) -> None:
        self._h = handlers

    async def on_transaction_start(self, conn: AsyncConnection, env: Envelope) -> None:
        await bind_tenant(conn, env.tenant_id)

    async def discover(self, conn: AsyncConnection, env: Envelope) -> None:
        p = env.payload
        try:
            cmd = DiscoverSchema(UUID(p["discovery_id"]), UUID(p["data_source_id"]),
                                 p["connector_id"], ref_from_json(p["object_ref"]),
                                 UUID(p["requested_by"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise PermanentError(f"DiscoverSchema payload noto‘g‘ri: {exc}") from exc
        scope = ConnectionScope(conn)
        await self._h.discover(scope.repo, scope.events, cmd, _ctx(env))

    async def configure(self, conn: AsyncConnection, env: Envelope) -> None:
        p = env.payload
        try:
            cmd = ConfigureSource(UUID(p["data_source_id"]), p["connector_id"],
                                  int(p["mapping_version"]), _mapping(p), UUID(p["approved_by"]),
                                  datetime.fromisoformat(p["approved_at"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise PermanentError(f"ConfigureSource payload noto‘g‘ri: {exc}") from exc
        scope = ConnectionScope(conn)
        await self._h.configure(scope.repo, scope.events, cmd, _ctx(env))

    async def sync(self, conn: AsyncConnection, env: Envelope) -> None:
        p = env.payload
        try:
            cmd = SyncSource(UUID(p["sync_run_id"]), UUID(p["data_source_id"]), p["connector_id"],
                             p["mode"], int(p["mapping_version"]), ref_from_json(p["object_ref"]),
                             UUID(p["requested_by"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise PermanentError(f"SyncSource payload noto‘g‘ri: {exc}") from exc
        await self._h.sync_requested(ConnectionScope(conn).repo, cmd, _ctx(env))

    def routes(self) -> dict[str, Any]:
        return {"DiscoverSchema.v1": self.discover, "ConfigureSource.v1": self.configure,
                "SyncSource.v1": self.sync}
