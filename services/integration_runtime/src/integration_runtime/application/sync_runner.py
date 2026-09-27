"""Navbatdagi sync run’larni lease bilan oladi va bajaradi.

Worker yiqilsa lease tugaydi va boshqa worker run’ni qayta oladi. Canonical fayl kaliti va
batch ID deterministik, batch yozuvi va eventlar bitta tranzaksiyada — shuning uchun qayta
bajarish ikkinchi batch yoki takroriy event bermaydi.
"""

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta

from ..domain.batch import RejectionReport, batch_id_for
from ..domain.canonical import CANONICAL_SCHEMA_VERSION
from ..ports.clock import Clock
from ..ports.connector import Connector, InvalidSource, SourceHandle, SourceUnavailable
from ..ports.repository import (
    TERMINAL_STATUSES,
    BatchRecord,
    IntegrationUnitOfWork,
    SyncRun,
    UnitOfWorkFactory,
)
from . import events
from .sync_engine import BatchOutput, SchemaChanged, SyncEngine

logger = logging.getLogger(__name__)


class SyncRunner:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        connectors: Mapping[str, Connector],
        engine: SyncEngine,
        clock: Clock,
        owner: str,
        lease: timedelta = timedelta(minutes=5),
        max_attempts: int = 5,
        retry_delay: timedelta = timedelta(seconds=30),
    ) -> None:
        self._uow = uow_factory
        self._connectors = dict(connectors)
        self._engine = engine
        self._clock = clock
        self._owner = owner
        self._lease = lease
        self._max_attempts = max_attempts
        self._retry_delay = retry_delay

    async def run_once(self) -> bool:
        """Bitta run’ni bajaradi. Navbat bo‘sh bo‘lsa False."""
        async with self._uow() as uow:
            claimed = await uow.repo.claim_run(self._owner, self._lease)
            await uow.commit()
        if claimed is None:
            return False

        async with self._uow() as uow:
            await uow.bind(claimed.tenant_id)
            run = await uow.repo.get_sync_run(claimed.sync_run_id)
            if run is None or run.status in TERMINAL_STATUSES:
                await uow.repo.complete_run(claimed.sync_run_id)
                await uow.commit()
                return True
            connector = self._connectors.get(run.connector_id)
            mapping = await uow.repo.get_mapping(run.data_source_id, run.mapping_version)
            problem: tuple[str, str] | None = None
            if connector is None:
                problem = ("mapping_invalid", f"Noma’lum connector: {run.connector_id}")
            elif mapping is None:
                problem = ("mapping_invalid",
                           f"Tasdiqlangan mapping {run.mapping_version}-versiyasi topilmadi")
            elif mapping.entity not in connector.manifest.supported_entities:
                problem = ("mapping_invalid", f"Connector {mapping.entity} ni qo‘llamaydi")
            elif connector.manifest.requires_object_ref and run.object_ref is None:
                problem = ("invalid_file", "Fayl ko‘rsatilmagan (object_ref yo‘q)")
            if problem is not None:
                await self._fail(uow, run, problem[0], problem[1], retryable=False)
                await uow.commit()
                return True
            await uow.repo.mark_running(run.id)
            await uow.commit()
        assert connector is not None and mapping is not None

        source = SourceHandle(run.tenant_id, run.data_source_id, run.object_ref, mapping.config)
        extracted_at = self._clock.now()

        async def heartbeat() -> None:
            async with self._uow() as hb:
                await hb.repo.extend_lease(run.id, self._owner, self._lease)
                await hb.commit()

        try:
            output = await self._engine.run(connector, source, mapping, sync_run_id=run.id,
                                            heartbeat=heartbeat)
        except SchemaChanged as exc:
            await self._fail_in_new_tx(run, "schema_changed", str(exc), retryable=False)
            return True
        except InvalidSource as exc:
            await self._fail_in_new_tx(run, "invalid_file", str(exc) or "Faylni o‘qib bo‘lmadi",
                                       retryable=False)
            return True
        except SourceUnavailable as exc:
            await self._retry_or_fail(run, claimed.attempts, "source_unavailable", str(exc))
            return True
        except Exception as exc:
            logger.exception("Sync run kutilmagan xato", extra={"sync_run_id": str(run.id)})
            await self._retry_or_fail(run, claimed.attempts, "internal", type(exc).__name__)
            return True

        await self._publish(run, connector, output, extracted_at)
        return True

    async def _publish(self, run: SyncRun, connector: Connector, output: BatchOutput,
                       extracted_at: datetime) -> None:
        batch = BatchRecord(
            id=batch_id_for(run.id, output.entity),
            tenant_id=run.tenant_id,
            sync_run_id=run.id,
            data_source_id=run.data_source_id,
            connector_id=connector.manifest.connector_id,
            connector_version=connector.manifest.version,
            entity=output.entity,
            canonical_schema_version=CANONICAL_SCHEMA_VERSION,
            record_count=output.record_count,
            object_ref=output.object_ref,
            extracted_at=extracted_at,
            is_full_snapshot=True,
        )
        async with self._uow() as uow:
            await uow.bind(run.tenant_id)
            if await uow.repo.insert_batch(batch):
                await uow.events.emit("SourceBatchReady.v1", events.source_batch_ready(batch),
                                      context=run.context, aggregate_id=run.id,
                                      aggregate_version=1)
                await uow.repo.finish_sync_run(
                    run.id, status="partial" if output.rejections.count else "succeeded",
                    record_count=output.record_count, rejections=output.rejections,
                    error_code=None,
                )
                await uow.events.emit(
                    "SyncRunCompleted.v1",
                    events.sync_run_completed(run, batch, output.rejections, self._clock.now()),
                    context=run.context, aggregate_id=run.id, aggregate_version=2,
                )
            await uow.repo.complete_run(run.id)
            await uow.commit()

    async def _retry_or_fail(self, run: SyncRun, attempts: int, code: str, message: str) -> None:
        if attempts < self._max_attempts:
            async with self._uow() as uow:
                await uow.repo.release_run(run.id, self._retry_delay * attempts)
                await uow.commit()
            return
        await self._fail_in_new_tx(run, code, message or code, retryable=True)

    async def _fail_in_new_tx(self, run: SyncRun, code: str, message: str, *,
                              retryable: bool) -> None:
        async with self._uow() as uow:
            await uow.bind(run.tenant_id)
            await self._fail(uow, run, code, message, retryable=retryable)
            await uow.commit()

    @staticmethod
    async def _fail(uow: IntegrationUnitOfWork, run: SyncRun, code: str, message: str, *,
                    retryable: bool) -> None:
        await uow.repo.finish_sync_run(run.id, status="failed", record_count=0,
                                       rejections=RejectionReport(), error_code=code)
        await uow.events.emit(
            "SyncRunFailed.v1",
            events.sync_run_failed(run, error_code=code, message=message, retryable=retryable),
            context=run.context, aggregate_id=run.id, aggregate_version=2,
        )
        await uow.repo.complete_run(run.id)
