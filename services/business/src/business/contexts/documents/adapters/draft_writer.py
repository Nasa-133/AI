"""DraftWriter porti: format bo‘yicha draft faylini yozish."""

from pathlib import Path

from ..domain.patch import ReplaceText
from ..domain.structure import Section
from ..ports.store import DocumentUnreadable
from .writer import DraftNotSupported, write_docx_draft, write_docx_from_sections, write_text_draft

PDF_NOTE = "PDF’dan tahrir yangi DOCX loyiha sifatida yaratildi — asl PDF joylashuvi saqlanmaydi."


class FileDraftWriter:
    def write(self, fmt: str, src: Path, dst: Path, ops: list[ReplaceText],
              sections: list[Section]) -> tuple[str, list[str]]:
        try:
            if fmt == "docx":
                return "docx", write_docx_draft(src, dst, ops)
            if fmt in ("txt", "md"):
                write_text_draft(dst, sections, markdown=fmt == "md")
                return fmt, []
            write_docx_from_sections(dst, sections)
            return "docx", [PDF_NOTE]
        except DraftNotSupported as exc:
            raise DocumentUnreadable(str(exc)) from exc
