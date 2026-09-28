"""Hujjat tuzilmasi: bo‘limlar (barqaror ID + odam o‘qiydigan manzil) va qidiruv parchalari."""

from dataclasses import dataclass
from enum import StrEnum

MAX_CHUNK_CHARS = 800


class SectionKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE_ROW = "table_row"
    PAGE_TEXT = "page_text"


@dataclass(frozen=True, slots=True)
class Section:
    section_id: str
    ordinal: int
    kind: SectionKind
    locator: str
    text: str


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    section_ids: tuple[str, ...]
    locator: str
    text: str


def chunk_sections(sections: list[Section], max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    """Sarlavhadan o‘tmaydigan ketma-ket bo‘limlar; sarlavha keyingi parchaga kontekst beradi."""
    chunks: list[Chunk] = []
    buf: list[Section] = []

    def flush() -> None:
        if not buf:
            return
        text = "\n".join(s.text for s in buf if s.text.strip())
        if text.strip():
            loc = buf[0].locator if len(buf) == 1 else f"{buf[0].locator} — {buf[-1].locator}"
            chunks.append(Chunk(len(chunks), tuple(s.section_id for s in buf), loc, text))
        buf.clear()

    for s in sections:
        if s.kind is SectionKind.HEADING:
            flush()
            buf.append(s)
            continue
        size = sum(len(x.text) + 1 for x in buf)
        if buf and size + len(s.text) > max_chars:
            flush()
        buf.append(s)
    flush()
    return chunks
