"""Yuklash → skaner → parse (alohida jarayon) → bo‘lim/parcha → embedding so‘rovi (TZ 9.2)."""

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ..domain.structure import Section, SectionKind, chunk_sections
from ..ports.store import (
    DocumentStore,
    DocumentUnreadable,
    FileStore,
    Outbox,
    Parser,
    VersionRecord,
)

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
CONTENT_TYPES = {"pdf": "application/pdf", "txt": "text/plain", "md": "text/markdown",
                 "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def sections_from(parsed: dict[str, Any]) -> list[Section]:
    return [Section(s["section_id"], s["ordinal"], SectionKind(s["kind"]), s["locator"], s["text"])
            for s in parsed["sections"]]


class DocumentIngest:
    def __init__(self, store: DocumentStore, files: FileStore, outbox: Outbox, parser: Parser,
                 tenant_id: UUID, *, redact: Callable[[str], str] = lambda text: text) -> None:
        """`redact` — AI’ga (embedding) ketadigan matndan shaxsiy ma’lumotni yashirish (TZ 13.12);
        qidiruv indeksi (FTS) va bo‘limlar Core’da asl matn bilan qoladi."""
        self._s, self._files, self._outbox, self._parser, self._t = (
            store, files, outbox, parser, tenant_id)
        self._redact = redact

    async def upload(self, user_id: UUID, filename: str, path: Path) -> dict[str, Any]:
        """Fayl diskda (hajm limiti yuklashda tekshirilgan). Parse — worker’da."""
        fmt = self._parser.detect_format(filename)
        self._parser.scan(path, fmt)  # tez rad etish; worker ham qayta tekshiradi
        document_id, version_id = uuid4(), uuid4()
        ref = await self._files.put_file(f"documents/{self._t}/{document_id}/{version_id}.{fmt}",
                                         path, content_type=CONTENT_TYPES[fmt])
        await self._s.create_document(document_id, filename.rsplit(".", 1)[0], user_id)
        await self._s.add_version(VersionRecord(
            version_id, document_id, 1, "original", None, filename, CONTENT_TYPES[fmt],
            ref["bucket"], ref["key"], ref["checksum_sha256"], ref["size_bytes"], "pending", None,
            {}, "none", None, user_id))
        await self._s.set_current(document_id, version_id)
        await self._outbox.publish("ProcessDocument.v1", {
            "document_id": str(document_id), "version_id": str(version_id)},
            aggregate_id=document_id, aggregate_version=1)
        return {"id": str(document_id), "version_id": str(version_id), "status": "pending"}

    async def process(self, document_id: UUID, version_id: UUID) -> None:
        version = await self._s.get_version(version_id)
        if version is None or version.parse_status not in ("pending", "parsing"):
            return  # takroriy yetkazish yoki allaqachon ishlangan
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"input.{version.fmt}"
            await self._files.download(version.object_ref(), path)
            try:
                self._parser.scan(path, version.fmt)
                parsed = await self._parser.parse(version.fmt, path)
            except DocumentUnreadable as exc:
                await self._s.set_parse(version_id, "failed", str(exc)[:1000], {})
                return
        sections = sections_from(parsed)
        quality = {**parsed["quality"], "sections": len(sections)}
        if parsed["quality"].get("needs_ocr"):
            # Skan PDF: bo‘sh fayl “o‘rganildi” deyilmaydi (D03).
            await self._s.set_parse(version_id, "needs_ocr", None, quality)
            await self._s.save_sections(version_id, sections)
            return
        await self._s.save_sections(version_id, sections)
        chunks = await self._s.save_chunks(document_id, version_id, chunk_sections(sections))
        await self._s.set_parse(version_id, "ready", None, quality)
        await self.request_embeddings(document_id, version_id, chunks)

    async def request_embeddings(self, document_id: UUID, version_id: UUID,
                                 chunks: list[tuple[UUID, str]]) -> None:
        if not chunks:
            return
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chunks.jsonl"
            path.write_text("".join(json.dumps({"chunk_id": str(c), "text": self._redact(t)},
                                               ensure_ascii=False) + "\n" for c, t in chunks),
                            encoding="utf-8")
            ref = await self._files.put_file(f"embeddings-in/{self._t}/{version_id}.jsonl", path,
                                             content_type="application/x-ndjson")
        await self._s.set_embedding_status(version_id, "pending")
        await self._outbox.publish("GenerateEmbeddings.v1", {
            "request_id": str(uuid4()), "document_version_id": str(version_id), "chunks_ref": ref,
            "chunk_count": len(chunks), "model_profile": "embedding_default"},
            aggregate_id=document_id, aggregate_version=1)

    async def embeddings_ready(self, payload: dict[str, Any]) -> None:
        version_id = UUID(payload["document_version_id"])
        if payload["status"] != "succeeded" or payload["vectors_ref"] is None:
            # Vektor bo‘lmasa ham qidiruv to‘liq matnli rejimda ishlaydi.
            await self._s.set_embedding_status(version_id, "failed")
            return
        rows = await self._files.read_jsonl(payload["vectors_ref"])
        vectors = {UUID(r["chunk_id"]): r["embedding"] for r in rows}
        await self._s.set_embeddings(version_id, vectors, payload["model"])
        await self._s.set_embedding_status(version_id, "ready")

    async def cleanup(self, document_id: UUID, job_id: UUID, keys: list[tuple[str, str]]) -> None:
        error = None
        for bucket, key in keys:
            try:
                await self._files.delete(bucket, key)
            except Exception as exc:
                error = f"{key}: {type(exc).__name__}"
        await self._s.finish_cleanup(document_id, job_id, error)
