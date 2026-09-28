"""Hujjatlar fon ishlari (TZ 17): tozalash job’ini qayta urinish va eski draftlarni o‘chirish."""

from ..ports.store import DocumentStore, FileStore, Outbox

MAX_CLEANUP_ATTEMPTS = 5


class DocumentMaintenance:
    def __init__(self, store: DocumentStore, files: FileStore, outbox: Outbox) -> None:
        self._s = store
        self._files = files
        self._outbox = outbox

    async def retry_cleanups(self) -> int:
        """Muvaffaqiyatsiz (yoki yo‘qolgan) tozalash — eksponensial kutish bilan qayta navbatga."""
        jobs = await self._s.retryable_cleanups(MAX_CLEANUP_ATTEMPTS)
        for document_id, job_id, attempts in jobs:
            await self._outbox.publish("CleanupDocument.v1", {
                "document_id": str(document_id), "cleanup_job_id": str(job_id)},
                aggregate_id=document_id, aggregate_version=100 + attempts)
        return len(jobs)

    async def purge_stale_drafts(self, days: int) -> int:
        """Joriy qilinmagan draftlar N kundan keyin (standart 90) o‘chiriladi: fayl va qatorlar."""
        drafts = await self._s.stale_drafts(days)
        for v in drafts:
            await self._files.delete(v.bucket, v.object_key)
            await self._s.delete_version(v.id)
        return len(drafts)
