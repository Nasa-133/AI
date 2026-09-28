"""Yuklangan fayl tuzilmasini tekshirish (TZ 9.2). ClamAV adapteri — P1; bu yer tuzilma qoidalari.

MIME va kengaytma mosligi, arxiv ochilish hajmi, makros, tashqi havola orqali avtomatik yuklash,
PDF’dagi skript/biriktirilgan fayllar.
"""

import re
import zipfile
from pathlib import Path

from .parsing import InvalidDocument

MAX_UNCOMPRESSED = 200 * 1024 * 1024
MAX_RATIO = 100
_PDF_ACTIVE = (b"/JavaScript", b"/JS ", b"/Launch", b"/EmbeddedFile", b"/RichMedia")
_KINDS = rb"(attachedTemplate|oleObject|frame)"
_EXTERNAL_REL = re.compile(rb'TargetMode="External"[^>]*Type="[^"]*' + _KINDS
                           + rb'|Type="[^"]*' + _KINDS + rb'"[^>]*TargetMode="External"')


def detect_format(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in {"pdf", "docx", "txt", "md"}:
        raise InvalidDocument("Qo‘llanadigan formatlar: PDF, DOCX, TXT, MD. PPTX va makrosli "
                              "fayllar P0 da qo‘llanmaydi.")
    return ext


def scan(path: Path, fmt: str) -> None:
    head = path.open("rb").read(8)
    if fmt == "pdf":
        if not head.startswith(b"%PDF"):
            raise InvalidDocument("Fayl kengaytmasi PDF, lekin mazmuni PDF emas.")
        data = path.read_bytes()
        if any(marker in data for marker in _PDF_ACTIVE):
            raise InvalidDocument("PDF’da skript yoki biriktirilgan fayl bor — xavfsizlik uchun "
                                  "qabul qilinmaydi. Oddiy PDF sifatida qayta saqlang.")
    elif fmt == "docx":
        if not head.startswith(b"PK"):
            raise InvalidDocument("Fayl kengaytmasi DOCX, lekin mazmuni DOCX emas.")
        _scan_docx(path)
    else:
        if b"\x00" in path.read_bytes()[:8192]:
            raise InvalidDocument("Matnli fayl kutilgan, lekin ikkilik ma’lumot topildi.")


def _scan_docx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            total = sum(i.file_size for i in infos)
            packed = max(1, sum(i.compress_size for i in infos))
            if total > MAX_UNCOMPRESSED or total / packed > MAX_RATIO:
                raise InvalidDocument("Arxiv ochilganda juda katta (zip-bomba ehtimoli).")
            names = {i.filename.lower() for i in infos}
            if any(n.endswith("vbaproject.bin") for n in names):
                raise InvalidDocument("Makrosli hujjatlar qabul qilinmaydi "
                                      "(DOCX makrossiz saqlang).")
            if "word/document.xml" not in names:
                raise InvalidDocument("DOCX tuzilmasi noto‘g‘ri (word/document.xml yo‘q).")
            for info in infos:
                if info.filename.lower().endswith(".rels") and _EXTERNAL_REL.search(
                        z.read(info.filename)):
                    raise InvalidDocument("Hujjat tashqi manbadan avtomatik yuklanadigan "
                                          "havolaga ega.")
    except zipfile.BadZipFile as exc:
        raise InvalidDocument("DOCX arxivi buzilgan.") from exc
