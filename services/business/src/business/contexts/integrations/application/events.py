"""Integration Runtime eventlari → data source proyeksiyasi (rad etilgan satrlar yashirilmaydi)."""

from typing import Any
from uuid import UUID

from ..domain.sources import SourceStatus
from ..ports.store import IntegrationsStore


class IntegrationEvents:
    def __init__(self, store: IntegrationsStore) -> None:
        self._s = store

    async def schema_discovered(self, p: dict[str, Any]) -> None:
        source_id = UUID(p["data_source_id"])
        if await self._s.get_source(source_id) is None:
            return
        if p["error_code"]:
            await self._s.update_source(source_id, status=SourceStatus.FAILED.value,
                                        error_message=p["error_message"] or p["error_code"])
            return
        await self._s.update_source(source_id, status=SourceStatus.AWAITING_MAPPING.value,
                                    discovery={"entities": p["entities"]}, error_message=None)

    async def source_configured(self, p: dict[str, Any]) -> None:
        source_id, version = UUID(p["data_source_id"]), int(p["mapping_version"])
        if await self._s.get_source(source_id) is None:
            return
        if p["accepted"]:
            await self._s.set_mapping_status(source_id, version, "accepted", None)
            await self._s.update_source(source_id, status=SourceStatus.READY.value,
                                        mapping_version=version, error_message=None)
        else:
            await self._s.set_mapping_status(source_id, version, "rejected", p["error_message"])
            await self._s.update_source(source_id, status=SourceStatus.AWAITING_MAPPING.value,
                                        error_message=p["error_message"])

    async def sync_completed(self, p: dict[str, Any]) -> None:
        source_id, run_id = UUID(p["data_source_id"]), UUID(p["sync_run_id"])
        await self._s.finish_sync_run(run_id, p["status"], p)
        message = None
        if p["rejected_count"]:
            message = (f"{p['rejected_count']} ta satr o‘qilmadi (masalan: "
                       f"{p['rejection_samples'][0]['reason']}).") if p["rejection_samples"] else (
                f"{p['rejected_count']} ta satr o‘qilmadi.")
        await self._s.update_source(source_id, status=SourceStatus.SYNCED.value,
                                    error_message=message)

    async def sync_failed(self, p: dict[str, Any]) -> None:
        source_id, run_id = UUID(p["data_source_id"]), UUID(p["sync_run_id"])
        await self._s.finish_sync_run(run_id, "failed", p)
        await self._s.update_source(source_id, status=SourceStatus.FAILED.value,
                                    error_message=f"{p['error_code']}: {p['message']}")
