"""Hujjat, versiya va bo‘lim saqlash (documents schema, RLS)."""

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.structure import Chunk, Section, SectionKind
from ..domain.text import normalize
from ..ports.store import DocumentRecord, VersionRecord

_DOC = (
    "SELECT d.id, d.title, d.current_version_id, d.visibility, d.status, d.created_by,"
    " d.created_at, d.updated_at, coalesce((SELECT array_agg(s.user_id) FROM"
    " documents.document_shares s WHERE s.document_id = d.id), '{}') AS shared_with"
    " FROM documents.documents d"
)
_VISIBLE = (" (:all OR d.created_by = :u OR d.visibility = 'tenant' OR EXISTS (SELECT 1 FROM"
            " documents.document_shares s WHERE s.document_id = d.id AND s.user_id = :u))")
_VERSION_COLS = (
    "id, document_id, version_no, kind, base_version_id, filename, content_type, bucket,"
    " object_key, sha256, size_bytes, parse_status, parse_error, quality, embedding_status,"
    " comment, created_by, created_at"
)


def _doc(r: Any) -> DocumentRecord:
    return DocumentRecord(r.id, r.title, r.current_version_id, r.visibility, r.status,
                          r.created_by, r.created_at, r.updated_at, frozenset(r.shared_with))


class SqlDocumentRecords:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._c = conn
        self._t = tenant_id

    async def create_document(self, document_id: UUID, title: str, user_id: UUID) -> None:
        await self._c.execute(text(
            "INSERT INTO documents.documents (tenant_id, id, title, created_by, created_at,"
            " updated_at) VALUES (:t, :id, :title, :by, now(), now())"),
            {"t": self._t, "id": document_id, "title": title[:300], "by": user_id})

    async def add_version(self, v: VersionRecord) -> None:
        await self._c.execute(text(
            f"INSERT INTO documents.versions (tenant_id, {_VERSION_COLS}) VALUES (:t, :id, :doc,"
            " :no, :kind, :base, :filename, :ct, :bucket, :key, :sha, :size, :ps, :pe,"
            " CAST(:q AS jsonb), :es, :comment, :by, now())"),
            {"t": self._t, "id": v.id, "doc": v.document_id, "no": v.version_no, "kind": v.kind,
             "base": v.base_version_id, "filename": v.filename, "ct": v.content_type,
             "bucket": v.bucket, "key": v.object_key, "sha": v.sha256, "size": v.size_bytes,
             "ps": v.parse_status, "pe": v.parse_error, "q": json.dumps(v.quality),
             "es": v.embedding_status, "comment": v.comment, "by": v.created_by})

    async def set_current(self, document_id: UUID, version_id: UUID) -> None:
        await self._c.execute(text(
            "UPDATE documents.documents SET current_version_id = :v, updated_at = now()"
            " WHERE id = :id"), {"v": version_id, "id": document_id})

    async def get(self, document_id: UUID) -> DocumentRecord | None:
        r = (await self._c.execute(text(_DOC + " WHERE d.id = :id AND d.status = 'active'"
                                        " FOR UPDATE OF d"), {"id": document_id})).first()
        return None if r is None else _doc(r)

    async def list_visible(self, *, user_id: UUID, see_all: bool, query: str | None,
                           limit: int) -> list[DocumentRecord]:
        rows = (await self._c.execute(text(
            _DOC + " WHERE d.status = 'active' AND" + _VISIBLE
            + " AND (CAST(:q AS text) IS NULL OR d.title ILIKE '%' || :q || '%')"
            " ORDER BY d.updated_at DESC LIMIT :n"),
            {"all": see_all, "u": user_id, "q": query, "n": limit})).all()
        return [_doc(r) for r in rows]

    async def get_version(self, version_id: UUID) -> VersionRecord | None:
        r = (await self._c.execute(text(
            f"SELECT {_VERSION_COLS} FROM documents.versions WHERE id = :id"),
            {"id": version_id})).first()
        return None if r is None else VersionRecord(*r)

    async def versions(self, document_id: UUID) -> list[VersionRecord]:
        rows = (await self._c.execute(text(
            f"SELECT {_VERSION_COLS} FROM documents.versions WHERE document_id = :d"
            " ORDER BY version_no DESC"), {"d": document_id})).all()
        return [VersionRecord(*r) for r in rows]

    async def next_version_no(self, document_id: UUID) -> int:
        r = await self._c.execute(text(
            "SELECT coalesce(max(version_no), 0) + 1 FROM documents.versions"
            " WHERE document_id = :d"),
            {"d": document_id})
        return int(r.scalar_one())

    async def set_parse(self, version_id: UUID, status: str, error: str | None,
                        quality: dict[str, Any]) -> None:
        await self._c.execute(text(
            "UPDATE documents.versions SET parse_status = :s, parse_error = :e,"
            " quality = CAST(:q AS jsonb) WHERE id = :id"),
            {"s": status, "e": error, "q": json.dumps(quality, ensure_ascii=False),
             "id": version_id})

    async def set_embedding_status(self, version_id: UUID, status: str) -> None:
        await self._c.execute(text(
            "UPDATE documents.versions SET embedding_status = :s WHERE id = :id"),
            {"s": status, "id": version_id})

    async def save_sections(self, version_id: UUID, sections: list[Section]) -> None:
        if not sections:
            return
        await self._c.execute(text(
            "INSERT INTO documents.sections (tenant_id, version_id, section_id, ordinal, kind,"
            " locator, text) VALUES (:t, :v, :sid, :o, :k, :loc, :txt)"),
            [{"t": self._t, "v": version_id, "sid": s.section_id, "o": s.ordinal,
              "k": s.kind.value, "loc": s.locator, "txt": s.text} for s in sections])

    async def sections(self, version_id: UUID) -> list[Section]:
        rows = (await self._c.execute(text(
            "SELECT section_id, ordinal, kind, locator, text FROM documents.sections"
            " WHERE version_id = :v ORDER BY ordinal"), {"v": version_id})).all()
        return [Section(r.section_id, r.ordinal, SectionKind(r.kind), r.locator, r.text)
                for r in rows]

    async def save_chunks(self, document_id: UUID, version_id: UUID,
                          chunks: list[Chunk]) -> list[tuple[UUID, str]]:
        rows = [(uuid4(), c) for c in chunks]
        if rows:
            await self._c.execute(text(
                "INSERT INTO documents.chunks (tenant_id, id, document_id, version_id, ordinal,"
                " section_ids, locator, text, search_text) VALUES (:t, :id, :d, :v, :o, :sids,"
                " :loc, :txt, :norm)"),
                [{"t": self._t, "id": cid, "d": document_id, "v": version_id, "o": c.ordinal,
                  "sids": list(c.section_ids), "loc": c.locator, "txt": c.text,
                  "norm": normalize(c.text)} for cid, c in rows])
        return [(cid, c.text) for cid, c in rows]

    async def chunks_of(self, version_id: UUID) -> list[tuple[UUID, str]]:
        rows = (await self._c.execute(text(
            "SELECT id, text FROM documents.chunks WHERE version_id = :v ORDER BY ordinal"),
            {"v": version_id})).all()
        return [(r.id, r.text) for r in rows]

    async def set_embeddings(self, version_id: UUID, vectors: dict[UUID, list[float]],
                             model: str) -> int:
        if not vectors:
            return 0
        result = await self._c.execute(text(
            "UPDATE documents.chunks SET embedding = CAST(:e AS vector), embedding_model = :m"
            " WHERE id = :id AND version_id = :v"),
            [{"e": json.dumps(vec), "m": model, "id": cid, "v": version_id}
             for cid, vec in vectors.items()])
        return int(result.rowcount or 0)

    async def mark_deleting(self, document_id: UUID) -> UUID:
        """Kirish darhol yopiladi va qidiruv parchalari o‘chiriladi (S03); fayllar — job orqali."""
        await self._c.execute(text(
            "UPDATE documents.documents SET status = 'deleting', deleted_at = now(),"
            " updated_at = now() WHERE id = :id"), {"id": document_id})
        await self._c.execute(text("DELETE FROM documents.chunks WHERE document_id = :id"),
                              {"id": document_id})
        job_id = uuid4()
        await self._c.execute(text(
            "INSERT INTO documents.cleanup_jobs (tenant_id, id, document_id, status, created_at)"
            " VALUES (:t, :id, :d, 'pending', now())"),
            {"t": self._t, "id": job_id, "d": document_id})
        return job_id

    async def finish_cleanup(self, document_id: UUID, job_id: UUID, error: str | None) -> None:
        await self._c.execute(text(
            "UPDATE documents.cleanup_jobs SET status = :s, attempts = attempts + 1,"
            " last_error = :e, finished_at = CASE WHEN :s = 'done' THEN now() END WHERE id = :id"),
            {"s": "failed" if error else "done", "e": error, "id": job_id})
        if not error:
            await self._c.execute(text(
                "UPDATE documents.documents SET status = 'deleted' WHERE id = :id"),
                {"id": document_id})

    async def set_access(self, document_id: UUID, visibility: str,
                         shared_with: frozenset[UUID], *, user_id: UUID) -> None:
        await self._c.execute(text(
            "UPDATE documents.documents SET visibility = :v, updated_at = now() WHERE id = :id"),
            {"v": visibility, "id": document_id})
        await self._c.execute(text(
            "DELETE FROM documents.document_shares WHERE document_id = :id"), {"id": document_id})
        if shared_with:
            await self._c.execute(text(
                "INSERT INTO documents.document_shares (tenant_id, document_id, user_id,"
                " created_by, created_at) VALUES (:t, :d, :u, :by, now())"),
                [{"t": self._t, "d": document_id, "u": u, "by": user_id} for u in shared_with])

    async def retryable_cleanups(self, max_attempts: int) -> list[tuple[UUID, UUID, int]]:
        # Kutish 10 · 2^urinish daqiqa (yo‘qolgan “pending” ham shu qoidaga tushadi).
        rows = (await self._c.execute(text(
            "SELECT document_id, id, attempts FROM documents.cleanup_jobs"
            " WHERE status IN ('failed', 'pending') AND attempts < :m"
            " AND created_at < now() - make_interval(mins => 10 * power(2, attempts)::int)"
            " ORDER BY created_at LIMIT 100"), {"m": max_attempts})).all()
        return [(r.document_id, r.id, r.attempts) for r in rows]

    async def stale_drafts(self, days: int) -> list[VersionRecord]:
        rows = (await self._c.execute(text(
            f"SELECT {_VERSION_COLS} FROM documents.versions v WHERE v.kind = 'draft'"
            " AND v.created_at < now() - make_interval(days => :d)"
            " AND NOT EXISTS (SELECT 1 FROM documents.documents d"
            "   WHERE d.current_version_id = v.id)"
            " AND NOT EXISTS (SELECT 1 FROM documents.versions c WHERE c.base_version_id = v.id)"
            " ORDER BY v.created_at LIMIT 200"), {"d": days})).all()
        return [VersionRecord(*r) for r in rows]

    async def delete_version(self, version_id: UUID) -> None:
        await self._c.execute(text("DELETE FROM documents.versions WHERE id = :id"),
                              {"id": version_id})
