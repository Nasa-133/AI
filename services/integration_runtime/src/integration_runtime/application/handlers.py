"""Command handler’lari. Har biri consumer tranzaksiyasi ichida ishlaydi (inbox bilan atomar)."""

import logging
from collections.abc import Mapping

from ..domain.mapping import SourceConfig, validate_mapping
from ..domain.templates import Suggestion, suggest
from ..ports.connector import (
    Connector,
    DiscoveredSource,
    InvalidSource,
    SourceHandle,
    SourceUnavailable,
)
from ..ports.repository import EventSink, IntegrationRepository, MessageContext, SyncRun
from . import events
from .commands import ConfigureSource, DiscoverSchema, SyncSource

logger = logging.getLogger(__name__)

MIN_SUGGESTION_SCORE = 0.5


class CommandHandlers:
    def __init__(self, connectors: Mapping[str, Connector]) -> None:
        self._connectors = dict(connectors)

    async def discover(self, repo: IntegrationRepository, sink: EventSink, cmd: DiscoverSchema,
                       ctx: MessageContext) -> None:
        found: list[tuple[DiscoveredSource, Suggestion]] = []
        error: tuple[str, str] | None = None
        connector = self._connectors.get(cmd.connector_id)
        if connector is None:
            error = ("unknown_connector", f"Noma’lum connector: {cmd.connector_id}")
        else:
            existing = await repo.ensure_data_source(ctx.tenant_id, cmd.data_source_id,
                                                     cmd.connector_id)
            if existing != cmd.connector_id:
                error = ("connector_mismatch",
                         f"Manba boshqa connector bilan bog‘langan: {existing}")
            elif connector.manifest.requires_object_ref and cmd.object_ref is None:
                error = ("invalid_file", "Fayl ko‘rsatilmagan (object_ref yo‘q)")
            else:
                handle = SourceHandle(ctx.tenant_id, cmd.data_source_id, cmd.object_ref,
                                      SourceConfig())
                try:
                    sources = await connector.discover_schema(handle)
                except InvalidSource as exc:
                    error = ("invalid_file", str(exc) or "Faylni o‘qib bo‘lmadi")
                except SourceUnavailable as exc:
                    error = ("source_unavailable", str(exc) or "Manba mavjud emas")
                else:
                    for source in sources:
                        candidates = suggest(source.columns)
                        good = [s for s in candidates if s.match_score >= MIN_SUGGESTION_SCORE]
                        found.extend((source, s) for s in (good or candidates[:1]))
        payload = events.schema_discovered(
            discovery_id=cmd.discovery_id, data_source_id=cmd.data_source_id,
            connector_id=cmd.connector_id, found=found,
            error_code=error[0] if error else None, error_message=error[1] if error else None,
        )
        await sink.emit("SchemaDiscovered.v1", payload, context=ctx,
                        aggregate_id=cmd.data_source_id, aggregate_version=0)

    async def configure(self, repo: IntegrationRepository, sink: EventSink,
                        cmd: ConfigureSource, ctx: MessageContext) -> None:
        errors: list[str] = []
        connector = self._connectors.get(cmd.connector_id)
        if connector is None:
            errors.append(f"Noma’lum connector: {cmd.connector_id}")
        elif cmd.mapping.entity not in connector.manifest.supported_entities:
            errors.append(f"{cmd.connector_id} {cmd.mapping.entity} entity’sini qo‘llamaydi")
        else:
            existing_connector = await repo.ensure_data_source(ctx.tenant_id, cmd.data_source_id,
                                                               cmd.connector_id)
            if existing_connector != cmd.connector_id:
                errors.append(f"Manba boshqa connector bilan bog‘langan: {existing_connector}")
        errors.extend(validate_mapping(cmd.mapping))
        if not errors:
            existing = await repo.get_mapping(cmd.data_source_id, cmd.mapping_version)
            if existing is None:
                await repo.add_mapping(
                    tenant_id=ctx.tenant_id, data_source_id=cmd.data_source_id,
                    version=cmd.mapping_version, mapping=cmd.mapping,
                    approved_by=cmd.approved_by, approved_at=cmd.approved_at,
                )
            elif existing != cmd.mapping:
                errors.append(f"{cmd.mapping_version}-versiya boshqa mapping bilan allaqachon "
                              "saqlangan; yangi versiya raqamini ishlating")
        payload = events.source_configured(cmd.data_source_id, cmd.mapping_version,
                                           accepted=not errors,
                                           error_message="; ".join(errors) or None)
        await sink.emit("SourceConfigured.v1", payload, context=ctx,
                        aggregate_id=cmd.data_source_id, aggregate_version=cmd.mapping_version)

    async def sync_requested(self, repo: IntegrationRepository, cmd: SyncSource,
                             ctx: MessageContext) -> None:
        """Tez tranzaksiya: faqat navbatga qo‘yiladi; bajarish SyncRunner’da."""
        await repo.ensure_data_source(ctx.tenant_id, cmd.data_source_id, cmd.connector_id)
        run = SyncRun(
            id=cmd.sync_run_id, tenant_id=ctx.tenant_id, data_source_id=cmd.data_source_id,
            connector_id=cmd.connector_id, mode=cmd.mode, mapping_version=cmd.mapping_version,
            object_ref=cmd.object_ref, requested_by=cmd.requested_by, status="queued",
            context=ctx,
        )
        if await repo.add_sync_run(run):
            await repo.enqueue_run(run.id, ctx.tenant_id)
        else:
            logger.info("Takroriy SyncSource e’tiborsiz qoldirildi",
                        extra={"sync_run_id": str(run.id)})
