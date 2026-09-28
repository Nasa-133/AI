"""Parser, skaner va draft yozuvchi (TZ 9.1–9.4, D03, D04). Sandbox — haqiqiy alohida jarayon."""

import hashlib
import zipfile
from pathlib import Path

import pytest

from business.contexts.documents.adapters.parsing import InvalidDocument, parse_docx, parse_text
from business.contexts.documents.adapters.sandbox import ParserTimeout, parse_isolated
from business.contexts.documents.adapters.scanner import detect_format, scan
from business.contexts.documents.adapters.writer import write_docx_draft
from business.contexts.documents.domain.patch import ReplaceText

from .samples import make_docx, make_pdf


def test_docx_sections_have_stable_paragraph_ids(tmp_path: Path) -> None:
    result = parse_docx(make_docx(tmp_path / "a.docx"))
    ids = {s["section_id"]: s for s in result["sections"]}
    assert ids["p1"]["kind"] == "heading" and ids["p2"]["locator"] == "¶2"
    assert ids["t1r1"]["text"] == "Summa | 1 000 000 so‘m"
    assert "sahifa" not in " ".join(s["locator"] for s in result["sections"])  # soxta sahifa yo‘q


async def test_pdf_text_and_scanned_detection_in_sandbox(tmp_path: Path) -> None:
    text = await parse_isolated("pdf", make_pdf(tmp_path / "t.pdf", ["Tolov 15 kun ichida.\n\nJarima 0.1%."]))
    assert text["quality"]["needs_ocr"] is False
    assert text["sections"][0]["locator"] == "sahifa 1, ¶1"
    scanned = await parse_isolated("pdf", make_pdf(tmp_path / "s.pdf", ["", ""]))
    assert scanned["quality"]["needs_ocr"] is True and scanned["sections"] == []  # D03


async def test_sandbox_reports_invalid_and_timeout(tmp_path: Path) -> None:
    broken = tmp_path / "b.pdf"
    broken.write_bytes(b"%PDF-1.4 garbage")
    with pytest.raises(InvalidDocument):
        await parse_isolated("pdf", broken)
    with pytest.raises(ParserTimeout):
        await parse_isolated("pdf", make_pdf(tmp_path / "x.pdf", ["a"]), limit_seconds=0.001)


def test_markdown_locators(tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_text("# To‘lov\n\nBirinchi.\n\nIkkinchi.\n", encoding="utf-8")
    locs = [s["locator"] for s in parse_text(p)["sections"]]
    assert locs == ["§ To‘lov", "§ To‘lov › ¶1", "§ To‘lov › ¶2"]


def test_scanner_rejects_dangerous_files(tmp_path: Path) -> None:
    assert detect_format("Shartnoma.DOCX") == "docx"
    with pytest.raises(InvalidDocument):
        detect_format("taqdimot.pptx")
    fake = tmp_path / "f.pdf"
    fake.write_bytes(b"PK\x03\x04 not a pdf")
    with pytest.raises(InvalidDocument):
        scan(fake, "pdf")
    js = tmp_path / "js.pdf"
    js.write_bytes(b"%PDF-1.4\n1 0 obj << /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>")
    with pytest.raises(InvalidDocument, match="skript"):
        scan(js, "pdf")
    macro = make_docx(tmp_path / "m.docx")
    with zipfile.ZipFile(macro, "a") as z:
        z.writestr("word/vbaProject.bin", b"x")
    with pytest.raises(InvalidDocument, match="Makros"):
        scan(macro, "docx")
    bomb = tmp_path / "bomb.docx"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"0" * (50 * 1024 * 1024))
    with pytest.raises(InvalidDocument, match="zip-bomba"):
        scan(bomb, "docx")
    scan(make_docx(tmp_path / "ok.docx"), "docx")


def test_d04_docx_draft_changes_only_target_and_keeps_style(tmp_path: Path) -> None:
    import docx

    src = make_docx(tmp_path / "src.docx")
    checksum = hashlib.sha256(src.read_bytes()).hexdigest()
    dst = tmp_path / "draft.docx"
    warnings = write_docx_draft(src, dst, [ReplaceText("p2", "15 kun", "30 kun")])
    assert warnings == []
    assert hashlib.sha256(src.read_bytes()).hexdigest() == checksum  # original o‘zgarmaydi
    old, new = parse_docx(src)["sections"], parse_docx(dst)["sections"]
    changed = [(a["section_id"], b["text"]) for a, b in zip(old, new, strict=True) if a != b]
    assert changed == [("p2", "To‘lov 30 kun ichida amalga oshiriladi.")]
    assert docx.Document(str(dst)).paragraphs[1].runs[0].italic is True


def test_docx_draft_across_runs_warns(tmp_path: Path) -> None:
    src = make_docx(tmp_path / "split.docx", split_run=True)
    dst = tmp_path / "d.docx"
    warnings = write_docx_draft(src, dst, [ReplaceText("p2", "15 kun", "30 kun")])
    assert warnings and parse_docx(dst)["sections"][1]["text"] == "To‘lov 30 kun ichida amalga oshiriladi."
