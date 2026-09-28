from dataclasses import dataclass
from uuid import UUID

from business.kernel.errors import BusinessError

from ..domain.access import MANAGERS, DocumentForbidden, can_view
from ..ports.store import DocumentRecord, DocumentStore, VersionRecord


class DocumentNotFound(BusinessError):
    """Ruxsatsiz hujjat mavjudligi oshkor qilinmaydi (TZ 15: 404)."""

    code = "NOT_FOUND"


@dataclass(frozen=True, slots=True)
class Viewer:
    user_id: UUID
    role: str

    @property
    def sees_all(self) -> bool:
        return self.role in MANAGERS


async def visible_document(store: DocumentStore, viewer: Viewer,
                           document_id: UUID) -> DocumentRecord:
    doc = await store.get(document_id)
    if doc is None or not can_view(doc.access, viewer.user_id, viewer.role):
        raise DocumentNotFound("Hujjat topilmadi.")
    return doc


async def version_of(store: DocumentStore, doc: DocumentRecord, version_id: UUID) -> VersionRecord:
    version = await store.get_version(version_id)
    if version is None or version.document_id != doc.id:
        raise DocumentNotFound("Hujjat versiyasi topilmadi.")
    return version


__all__ = ["DocumentForbidden", "DocumentNotFound", "Viewer", "version_of", "visible_document"]
