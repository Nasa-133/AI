"""Qidiruv: ACL qamrovi, to‘liq matnli (o‘zbekcha qo‘shimchalar uchun prefiks) va vektorli."""

import json
import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..ports.store import SearchHit, SearchScope
from .sql_docs import _VISIBLE

_HIT = (
    "SELECT c.document_id, d.title, c.version_id, v.version_no, c.id, c.section_ids, c.locator,"
    " c.text, {score} AS score FROM documents.chunks c"
    " JOIN documents.documents d ON d.tenant_id = c.tenant_id AND d.id = c.document_id"
    " JOIN documents.versions v ON v.tenant_id = c.tenant_id AND v.id = c.version_id"
    " WHERE c.version_id = ANY(:versions) AND d.status = 'active'"
)
_TOKEN = re.compile(r"[a-z0-9]+")


def tsquery(terms: list[str]) -> str | None:
    """Faqat [a-z0-9] bo‘laklari (normallashtirilgan) — tsquery sintaksisini buzib bo‘lmaydi.

    Prefiks (`:*`) o‘zbekcha qo‘shimchalarni qamraydi: “muddat” → muddati, muddatlar.
    Postgres parseri tutuq belgisida bo‘ladi (to'lov → to, lov) — indeks ham shunday.
    """
    parts = [p for t in terms for p in _TOKEN.findall(t) if len(p) > 1]
    return " | ".join(f"{p}:*" for p in dict.fromkeys(parts)) or None


def _hit(r: object) -> SearchHit:
    return SearchHit(r.document_id, r.title, r.version_id, r.version_no, r.id,  # type: ignore[attr-defined]
                     list(r.section_ids), r.locator, r.text, float(r.score))  # type: ignore[attr-defined]


class SqlDocumentSearch:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._c = conn
        self._t = tenant_id

    async def search_scope(self, *, user_id: UUID, see_all: bool,
                           document_ids: list[UUID] | None) -> SearchScope:
        rows: list[UUID] = list((await self._c.execute(text(
            "SELECT d.current_version_id FROM documents.documents d"
            " JOIN documents.versions v"
            " ON v.tenant_id = d.tenant_id AND v.id = d.current_version_id"
            " WHERE d.status = 'active' AND v.parse_status = 'ready' AND" + _VISIBLE
            + " AND (CAST(:ids AS uuid[]) IS NULL OR d.id = ANY(CAST(:ids AS uuid[])))"),
            {"all": see_all, "u": user_id, "ids": document_ids})).scalars().all())
        return SearchScope(rows)

    async def search_text(self, scope: SearchScope, terms: list[str],
                          limit: int) -> list[SearchHit]:
        query = tsquery(terms)
        if not scope.version_ids or query is None:
            return []
        rows = (await self._c.execute(text(
            _HIT.format(score="ts_rank(c.tsv, to_tsquery('simple', :q))")
            + " AND c.tsv @@ to_tsquery('simple', :q) ORDER BY score DESC LIMIT :n"),
            {"versions": scope.version_ids, "q": query, "n": limit})).all()
        return [_hit(r) for r in rows]

    async def search_vector(self, scope: SearchScope, vector: list[float],
                            limit: int) -> list[SearchHit]:
        if not scope.version_ids:
            return []
        rows = (await self._c.execute(text(
            _HIT.format(score="1 - (c.embedding <=> CAST(:vec AS vector))")
            + " AND c.embedding IS NOT NULL AND vector_dims(c.embedding) = :dim"
            " ORDER BY c.embedding <=> CAST(:vec AS vector) LIMIT :n"),
            {"versions": scope.version_ids, "vec": json.dumps(vector), "dim": len(vector),
             "n": limit})).all()
        return [_hit(r) for r in rows]
