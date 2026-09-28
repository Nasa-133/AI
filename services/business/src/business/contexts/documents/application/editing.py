"""Xavfsiz tahrir (TZ 9.4): draft (asl o‘zgarmaydi), asosiy versiya (409), o‘chirish, ulashish."""

import tempfile
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from ..domain.access import DocumentForbidden, can_draft, can_promote
from ..domain.patch import ReplaceText, apply, diff, ensure_current
from ..domain.structure import Section, chunk_sections
from ..ports.store import DocumentStore, FileStore, Outbox, VersionRecord
from .common import DocumentNotFound, Viewer, version_of, visible_document
from .ingest import CONTENT_TYPES, DocumentIngest


class DraftWriter(Protocol):
    """Adapter: base fayldan draft faylini yozadi; ogohlantirishlar ro‘yxatini qaytaradi."""

    def write(self, fmt: str, src: Path, dst: Path, ops: list[ReplaceText],
              sections: list[Section]) -> tuple[str, list[str]]:
        """Natija formati (pdf → docx) va ogohlantirishlar."""
        ...


class DraftNotReady(DocumentNotFound):
    code = "DOCUMENT_NOT_READY"


class DocumentEditing:
    def __init__(self, store: DocumentStore, files: FileStore, outbox: Outbox,
                 writer: DraftWriter, ingest: DocumentIngest, tenant_id: UUID) -> None:
        self._s, self._files, self._outbox, self._writer, self._ingest, self._t = (
            store, files, outbox, writer, ingest, tenant_id)

    async def create_draft(self, viewer: Viewer, document_id: UUID, base_version_id: UUID,
                           expected_version_id: UUID, ops: list[ReplaceText],
                           comment: str | None) -> dict[str, Any]:
        doc = await visible_document(self._s, viewer, document_id)
        if not can_draft(doc.access, viewer.user_id, viewer.role):
            raise DocumentForbidden("Bu hujjat uchun tahrir (draft) huquqi yo‘q.")
        # Kutilgan versiya hali joriy bo‘lmasa — yashirin overwrite yo‘q (D05).
        ensure_current(doc.current_version_id, expected_version_id)
        base = await version_of(self._s, doc, base_version_id)
        if base.parse_status != "ready":
            raise DraftNotReady("Hujjat hali o‘qilmagan yoki o‘qib bo‘lmadi — tahrir mumkin emas.")
        sections = await self._s.sections(base.id)
        new_sections = apply(ops, sections)  # noaniq nishon — PatchTargetInvalid
        draft_id = uuid4()
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / f"base.{base.fmt}", Path(tmp) / "draft"
            await self._files.download(base.object_ref(), src)
            fmt, warnings = self._writer.write(base.fmt, src, dst, ops, new_sections)
            ref = await self._files.put_file(
                f"documents/{self._t}/{document_id}/{draft_id}.{fmt}", dst,
                content_type=CONTENT_TYPES[fmt])
        filename = base.filename.rsplit(".", 1)[0] + f".{fmt}"
        version_no = await self._s.next_version_no(document_id)
        await self._s.add_version(VersionRecord(
            draft_id, document_id, version_no, "draft", base.id, filename, CONTENT_TYPES[fmt],
            ref["bucket"], ref["key"], ref["checksum_sha256"], ref["size_bytes"], "ready", None,
            {**base.quality, "warnings": [*base.quality.get("warnings", []), *warnings]},
            "none", comment, viewer.user_id))
        await self._s.save_sections(draft_id, new_sections)
        await self._s.save_chunks(document_id, draft_id, chunk_sections(new_sections))
        changes, _ = diff(sections, new_sections)
        return {"document_id": str(document_id), "draft_version_id": str(draft_id),
                "version_no": version_no, "warnings": warnings,
                "changes": [{"section_id": c.section_id, "locator": c.locator,
                             "change": c.change.value, "before": c.before, "after": c.after}
                            for c in changes]}

    async def promote(self, viewer: Viewer, document_id: UUID, version_id: UUID,
                      expected_current_version_id: UUID) -> dict[str, Any]:
        """“Asosiy versiya qilish” — foydalanuvchi amali, alohida vakolat (TZ 9.4)."""
        doc = await visible_document(self._s, viewer, document_id)
        if not can_promote(doc.access, viewer.user_id, viewer.role):
            raise DocumentForbidden("Asosiy versiyani almashtirish huquqi yo‘q.")
        ensure_current(doc.current_version_id, expected_current_version_id)
        version = await version_of(self._s, doc, version_id)
        await self._s.set_current(document_id, version.id)
        if version.embedding_status == "none":
            # Draft parchalari yaratilishda saqlangan; endi qidiruvga kirgani uchun vektorlanadi.
            await self._ingest.request_embeddings(document_id, version.id,
                                                  await self._s.chunks_of(version.id))
        return {"document_id": str(document_id), "current_version_id": str(version.id)}

    async def delete(self, viewer: Viewer, document_id: UUID) -> dict[str, Any]:
        doc = await visible_document(self._s, viewer, document_id)
        if not can_promote(doc.access, viewer.user_id, viewer.role):
            raise DocumentForbidden("Hujjatni o‘chirish huquqi yo‘q.")
        versions = await self._s.versions(document_id)
        job_id = await self._s.mark_deleting(document_id)
        await self._outbox.publish("CleanupDocument.v1", {
            "document_id": str(document_id), "cleanup_job_id": str(job_id)},
            aggregate_id=document_id, aggregate_version=len(versions) + 1)
        return {"document_id": str(document_id), "status": "deleting",
                "cleanup_job_id": str(job_id)}

    async def share(self, viewer: Viewer, document_id: UUID, visibility: str,
                    user_ids: list[UUID]) -> None:
        doc = await visible_document(self._s, viewer, document_id)
        if not can_promote(doc.access, viewer.user_id, viewer.role):
            raise DocumentForbidden("Ulashish huquqi yo‘q.")
        await self._s.set_access(document_id, visibility, frozenset(user_ids),
                                 user_id=viewer.user_id)
