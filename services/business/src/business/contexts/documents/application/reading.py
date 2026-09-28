"""O‘qish: ro‘yxat, tafsilot, qidiruv (gibrid, ACL oldin), bo‘lim, versiyalarni solishtirish."""

from typing import Any
from uuid import UUID

from ..domain.access import can_draft, can_promote
from ..domain.patch import diff
from ..domain.text import query_terms
from ..ports.store import DocumentStore, QueryEmbedder, SearchHit, VersionRecord
from .common import DocumentNotFound, Viewer, version_of, visible_document

RRF_K = 60


def version_view(v: VersionRecord, current_id: UUID | None) -> dict[str, Any]:
    return {"id": str(v.id), "version_no": v.version_no, "kind": v.kind,
            "base_version_id": str(v.base_version_id) if v.base_version_id else None,
            "filename": v.filename, "parse_status": v.parse_status, "parse_error": v.parse_error,
            "quality": v.quality, "embedding_status": v.embedding_status, "comment": v.comment,
            "sha256": v.sha256.strip(), "size_bytes": v.size_bytes,
            "is_current": v.id == current_id,
            "created_at": v.created_at.isoformat() if v.created_at else None}


def fuse(text_hits: list[SearchHit], vector_hits: list[SearchHit], limit: int) -> list[SearchHit]:
    """Reciprocal Rank Fusion: ikki ro‘yxatda ham yuqori bo‘lgan parcha birinchi."""
    scores: dict[UUID, float] = {}
    by_id: dict[UUID, SearchHit] = {}
    for hits in (text_hits, vector_hits):
        for rank, hit in enumerate(hits):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1 / (RRF_K + rank + 1)
            by_id.setdefault(hit.chunk_id, hit)
    ranked = sorted(scores, key=lambda cid: -scores[cid])[:limit]
    return [SearchHit(**{**{f: getattr(by_id[c], f) for f in SearchHit.__dataclass_fields__},
                         "score": round(scores[c], 6)}) for c in ranked]


class DocumentReading:
    def __init__(self, store: DocumentStore, embedder: QueryEmbedder | None = None) -> None:
        self._s = store
        self._embedder = embedder

    async def list_documents(self, viewer: Viewer,
                             query: str | None = None) -> list[dict[str, Any]]:
        out = []
        for d in await self._s.list_visible(user_id=viewer.user_id, see_all=viewer.sees_all,
                                            query=query, limit=200):
            current = (await self._s.get_version(d.current_version_id)
                       if d.current_version_id else None)
            view = version_view(current, d.current_version_id) if current else None
            out.append({"id": str(d.id), "title": d.title, "visibility": d.visibility,
                        "updated_at": d.updated_at.isoformat(), "current": view})
        return out

    async def detail(self, viewer: Viewer, document_id: UUID) -> dict[str, Any]:
        d = await visible_document(self._s, viewer, document_id)
        return {"id": str(d.id), "title": d.title, "visibility": d.visibility,
                "shared_with": sorted(str(u) for u in d.shared_with),
                "current_version_id": str(d.current_version_id) if d.current_version_id else None,
                "can_draft": can_draft(d.access, viewer.user_id, viewer.role),
                "can_promote": can_promote(d.access, viewer.user_id, viewer.role),
                "versions": [version_view(v, d.current_version_id)
                             for v in await self._s.versions(document_id)]}

    async def sections(self, viewer: Viewer, document_id: UUID,
                       version_id: UUID) -> list[dict[str, Any]]:
        d = await visible_document(self._s, viewer, document_id)
        await version_of(self._s, d, version_id)
        return [{"section_id": s.section_id, "kind": s.kind.value, "locator": s.locator,
                 "text": s.text} for s in await self._s.sections(version_id)]

    async def search(self, viewer: Viewer, query: str, document_ids: list[UUID] | None,
                     limit: int = 8) -> dict[str, Any]:
        scope = await self._s.search_scope(user_id=viewer.user_id, see_all=viewer.sees_all,
                                           document_ids=document_ids)
        text_hits = await self._s.search_text(scope, query_terms(query), limit * 2)
        vector = await self._embedder.embed(query) if self._embedder and scope.version_ids else None
        vector_hits = await self._s.search_vector(scope, vector, limit * 2) if vector else []
        results = fuse(text_hits, vector_hits, limit)
        notes = [] if vector is not None or not scope.version_ids else [
            "Semantik qidiruv vaqtincha mavjud emas — faqat matn bo‘yicha qidirildi."]
        return {"mode": "hybrid" if vector is not None else "full_text", "notes": notes,
                "results": [{"document_id": str(h.document_id), "document_title": h.document_title,
                             "version_id": str(h.version_id), "version_no": h.version_no,
                             "chunk_id": str(h.chunk_id), "section_ids": h.section_ids,
                             "locator": h.locator, "text": h.text, "score": h.score}
                            for h in results]}

    async def read_section(self, viewer: Viewer, document_id: UUID, version_id: UUID,
                           section_id: str) -> dict[str, Any]:
        d = await visible_document(self._s, viewer, document_id)
        await version_of(self._s, d, version_id)
        section = next((s for s in await self._s.sections(version_id)
                        if s.section_id == section_id), None)
        if section is None:
            raise DocumentNotFound("Bo‘lim topilmadi.")
        return {"document_id": str(document_id), "version_id": str(version_id),
                "section_id": section_id, "locator": section.locator, "kind": section.kind.value,
                "text": section.text}

    async def compare(self, viewer: Viewer, document_id: UUID, left_id: UUID,
                      right_id: UUID) -> dict[str, Any]:
        d = await visible_document(self._s, viewer, document_id)
        await version_of(self._s, d, left_id)
        await version_of(self._s, d, right_id)
        changes, unchanged = diff(await self._s.sections(left_id),
                                  await self._s.sections(right_id))
        return {"document_id": str(document_id), "left_version_id": str(left_id),
                "right_version_id": str(right_id), "unchanged_count": unchanged,
                "changes": [{"section_id": c.section_id, "locator": c.locator,
                             "change": c.change.value, "before": c.before, "after": c.after}
                            for c in changes]}
