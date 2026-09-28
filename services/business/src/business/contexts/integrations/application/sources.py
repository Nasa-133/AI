"""Yuklash → data source → mapping tasdiqlash → sync (docs/design/stage1.md §4). Core faqat
command yuboradi va proyeksiyani yangilaydi; vendor bilimi Integration Runtime’da."""

from datetime import UTC, datetime
from typing import IO, Any
from uuid import UUID, uuid4

from business.kernel.errors import BusinessError

from ..domain.sources import (
    AUTO_SYNC_CONNECTORS,
    AlreadyConnected,
    SourceNotReady,
    SourceStatus,
    check_upload,
    requires_file,
)
from ..ports.store import FileStore, IntegrationsStore, Outbox


class NotFound(BusinessError):
    code = "NOT_FOUND"


def _ref(upload: dict[str, Any]) -> dict[str, Any]:
    return {"bucket": upload["bucket"], "key": upload["object_key"],
            "checksum_sha256": upload["sha256"].strip(), "size_bytes": upload["size_bytes"]}


class SourceService:
    def __init__(self, store: IntegrationsStore, files: FileStore, outbox: Outbox,
                 tenant_id: UUID) -> None:
        self._s, self._files, self._outbox, self._t = store, files, outbox, tenant_id

    async def upload(self, user_id: UUID, filename: str, content_type: str, data: IO[bytes],
                     purpose: str) -> dict[str, Any]:
        name, limit = check_upload(filename, purpose)
        upload_id = uuid4()
        ref = await self._files.put(f"uploads/{self._t}/{upload_id}/{name}", data,
                                    max_bytes=limit, content_type=content_type)
        await self._s.add_upload({"id": upload_id, "purpose": purpose, "filename": name,
                                  "ct": content_type, "size": ref["size_bytes"],
                                  "sha": ref["checksum_sha256"], "bucket": ref["bucket"],
                                  "key": ref["key"], "by": user_id})
        return {"id": str(upload_id), "filename": name, "size_bytes": ref["size_bytes"],
                "sha256": ref["checksum_sha256"], "purpose": purpose}

    async def create(self, user_id: UUID, connector_id: str, name: str,
                     upload_id: UUID | None, entity: str | None = None) -> dict[str, Any]:
        """`entity` — ixtiyoriy ishora: ko‘p obyektli manbada (ERP) qaysi obyekt ulanmoqda."""
        object_ref = None
        if requires_file(connector_id):
            upload = await self._s.get_upload(upload_id) if upload_id else None
            if upload is None or upload["purpose"] != "dataset_import":
                raise NotFound("Analitik import uchun yuklangan fayl topilmadi.")
            object_ref = _ref(upload)
        source_id = uuid4()
        await self._s.add_source({"id": source_id, "name": name.strip()[:200] or connector_id,
                                  "connector": connector_id, "upload": upload_id,
                                  "status": SourceStatus.DISCOVERING.value, "by": user_id})
        if entity:
            await self._ensure_not_connected(None, connector_id, entity, upload_id)
            await self._s.update_source(source_id, entity=entity)
        await self._outbox.publish("DiscoverSchema.v1", {
            "discovery_id": str(uuid4()), "data_source_id": str(source_id),
            "connector_id": connector_id, "object_ref": object_ref, "requested_by": str(user_id)},
            aggregate_id=source_id, aggregate_version=1)
        return {"id": str(source_id), "status": SourceStatus.DISCOVERING.value}

    async def approve_mapping(self, user_id: UUID, source_id: UUID, entity: str,
                              mapping: list[dict[str, Any]],
                              status_map: list[dict[str, str]]) -> dict[str, Any]:
        source = await self._require(source_id)
        if source["status"] in (SourceStatus.DISCOVERING, SourceStatus.SYNCING):
            raise SourceNotReady("Manba hozir band — natijani kuting.")
        await self._ensure_not_connected(source_id, source["connector_id"], entity,
                                         source["upload_id"])
        version = await self._s.next_mapping_version(source_id)
        config = {"delimiter": ",", "encoding": "utf-8", "status_map": status_map}
        now = datetime.now(UTC)
        await self._s.add_mapping({"source": source_id, "version": version, "entity": entity,
                                   "config": config, "mapping": mapping, "by": user_id,
                                   "at": now})
        await self._s.update_source(source_id, status=SourceStatus.CONFIGURING.value,
                                    entity=entity, error_message=None)
        await self._outbox.publish("ConfigureSource.v1", {
            "data_source_id": str(source_id), "connector_id": source["connector_id"],
            "mapping_version": version, "entity": entity, "config": config, "mapping": mapping,
            "approved_by": str(user_id), "approved_at": now.isoformat()},
            aggregate_id=source_id, aggregate_version=version)
        return {"id": str(source_id), "mapping_version": version,
                "status": SourceStatus.CONFIGURING.value}

    async def sync(self, user_id: UUID, source_id: UUID) -> dict[str, Any]:
        source = await self._require(source_id)
        retry_failed = source["status"] == SourceStatus.FAILED and source["mapping_version"]
        if source["status"] not in (SourceStatus.READY, SourceStatus.SYNCED) and not retry_failed:
            raise SourceNotReady("Avval mapping’ni tasdiqlang (manba tayyor emas).")
        object_ref = None
        if requires_file(source["connector_id"]):
            upload = await self._s.get_upload(source["upload_id"])
            assert upload is not None
            object_ref = _ref(upload)
        run_id = uuid4()
        await self._s.add_sync_run({"id": run_id, "source": source_id,
                                    "version": source["mapping_version"], "by": user_id})
        await self._s.update_source(source_id, status=SourceStatus.SYNCING.value,
                                    last_sync_run_id=run_id, error_message=None)
        await self._outbox.publish("SyncSource.v1", {
            "sync_run_id": str(run_id), "data_source_id": str(source_id),
            "connector_id": source["connector_id"], "mode": "full", "object_ref": object_ref,
            "requested_by": str(user_id), "mapping_version": source["mapping_version"]},
            aggregate_id=source_id, aggregate_version=source["mapping_version"])
        return {"sync_run_id": str(run_id), "status": SourceStatus.SYNCING.value}

    async def auto_sync(self, interval_seconds: int) -> int:
        """Fon ishi: tashqi tizim manbalari oxirgi sinxrondan `interval` o‘tgach qayta o‘qiladi.

        Muvaffaqiyatsiz sinxron ham shu oraliqda qayta uriniladi (ERP tiklangach o‘zi tuzaladi).
        So‘rovchi — manbani ulagan foydalanuvchi (audit va sync_runs.requested_by uchun).
        """
        started = 0
        for row in await self._s.due_for_auto_sync(AUTO_SYNC_CONNECTORS, interval_seconds):
            await self.sync(row["created_by"], row["id"])
            started += 1
        return started

    async def _ensure_not_connected(self, source_id: UUID | None, connector_id: str,
                                    entity: str, upload_id: UUID | None) -> None:
        sha = None
        if upload_id is not None:
            upload = await self._s.get_upload(upload_id)
            sha = upload["sha256"].strip() if upload else None
        same = await self._s.find_same_source(source_id, connector_id, entity, sha)
        if same is not None:
            what = "Bu fayl" if sha else "Bu tizim"
            raise AlreadyConnected(f"{what} shu ma’lumot turi uchun allaqachon ulangan "
                                   f"(“{same['name']}”). Bitta bazani ikki marta ulash mumkin "
                                   "emas — raqamlar ikki marta sanalardi.")

    async def detail(self, source_id: UUID) -> dict[str, Any]:
        return await self._require(source_id)

    async def _require(self, source_id: UUID) -> dict[str, Any]:
        source = await self._s.get_source(source_id)
        if source is None:
            raise NotFound("Data source topilmadi.")
        return source
