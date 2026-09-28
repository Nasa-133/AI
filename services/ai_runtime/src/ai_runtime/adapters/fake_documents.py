"""FakeProvider’ning hujjat rejasi: savol → qidiruv → iqtibosli javob; tahrir → draft.

Hujjat matni faqat iqtibos sifatida ko‘rsatiladi — undagi “ko‘rsatmalar” reja tanloviga
ta’sir qilmaydi (TZ 9.4, D06): reja faqat foydalanuvchi xabaridan tuziladi.
"""

import re
from dataclasses import dataclass
from typing import Any

from ..application.commands import CONTEXT_PREFIX

_APOSTROPHES = str.maketrans({c: "'" for c in "‘’ʻʼ`´"})
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_CONTEXT_RE = re.compile(rf"document_id=({_UUID})")
_EDIT_RE = re.compile(
    r"[\"“«](?P<find>[^\"”»]{1,200})[\"”»]\s*-?\s*ni\s+[\"“«](?P<replace>[^\"”»]{0,200})[\"”»]"
    r"\s*-?\s*ga\s+(?:o'zgartir|almashtir|tuzat)", re.IGNORECASE)
_DOCUMENT_RE = re.compile(r"\b(hujjat|shartnoma|band|nizom|buyruq|reglament|kelishuv)")
_STOP_PREFIXES = ("hujjat", "shartnom", "qancha", "necha", "qanday", "qaysi", "qachon", "qayer",
                  "bo'yicha", "haqida", "yozilgan", "deyilgan", "ko'rsat", "aytib", "menga")
_STOP_WORDS = {"nima", "kim", "bormi", "bor", "yo'q", "uchun", "va", "yoki", "bu", "shu", "u",
               "da", "ni", "men", "ayt", "ber", "qil", "mi", "esa", "ham", "qanaqa"}
MAX_QUOTES = 3
QUOTE_CHARS = 400


def _norm(text: str) -> str:
    return " ".join(text.translate(_APOSTROPHES).lower().split())


def _stem(word: str) -> str:
    return word.replace("'", "")[:5]


@dataclass(frozen=True, slots=True)
class Edit:
    find: str
    replace: str


def parse_edit(text: str) -> Edit | None:
    m = _EDIT_RE.search(text.translate(_APOSTROPHES))
    return Edit(m.group("find").strip(), m.group("replace").strip()) if m else None


def context_document_ids(items: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for item in items:
        content = item.get("content")
        if item.get("role") == "developer" and isinstance(content, str) \
                and content.startswith(CONTEXT_PREFIX):
            ids += _CONTEXT_RE.findall(content)
    return list(dict.fromkeys(ids))


def is_document_request(text: str, available: set[str], has_context: bool) -> bool:
    if "search_documents" not in available:
        return False
    if has_context or "list_available_metrics" not in available:
        return True
    return _DOCUMENT_RE.search(_norm(text)) is not None or parse_edit(text) is not None


_ADDRESS = re.compile(r"^\s*@?[\w']+\s*,\s*")  # “Dilnoza, …” — murojaat, savol emas


def content_terms(question: str) -> list[str]:
    words = re.findall(r"[\w']+", _norm(_ADDRESS.sub("", question, count=1)))
    return [w for w in words if len(w.strip("'")) > 1 and w not in _STOP_WORDS
            and not w.startswith(_STOP_PREFIXES)]


def is_relevant(hit_text: str, terms: list[str]) -> bool:
    """Qidiruv OR va vektor bo‘yicha ishlaydi — javob uchun so‘zlarning kamida yarmi mos bo‘lsin."""
    if not terms:
        return False
    stems = {_stem(w) for w in re.findall(r"[\w']+", _norm(hit_text))}
    matched = sum(1 for t in terms if _stem(t) in stems)
    return matched > 0 and matched * 2 >= len(terms)


def search_query(text: str) -> str:
    edit = parse_edit(text)
    if edit:
        return edit.find
    terms = content_terms(text)
    return " ".join(terms)[:500] or text.strip()[:500]


def _quote(text: str) -> str:
    short = text if len(text) <= QUOTE_CHARS else text[:QUOTE_CHARS].rstrip() + "…"
    # Iqtibos markdown sifatida talqin qilinmasin: har qator blockquote ichida.
    return "\n".join("> " + line for line in short.splitlines() if line.strip())


def _cite(hit: dict[str, Any]) -> str:
    return f"— *{hit['document_title']}*, v{hit['version_no']}, {hit['locator']}"


def answer_question(question: str, search: dict[str, Any]) -> tuple[str, bool]:
    """(javob matni, topildimi)."""
    terms = content_terms(question)
    hits = [h for h in search["results"] if is_relevant(h["text"], terms)]
    notes = list(search.get("notes") or [])
    if not hits:
        text = ("Hujjatda topilmadi: tanlangan hujjatlarda bu savolga javob beradigan bo‘lim "
                "yo‘q. Taxminiy javob bermayman — boshqa hujjatni tanlang yoki savolni "
                "aniqlashtiring.")
        return "\n\n".join([text, *notes]), False
    parts = ["Hujjatda shunday yozilgan:"]
    for hit in hits[:MAX_QUOTES]:
        parts.append(f"{_quote(hit['text'])}\n\n{_cite(hit)}")
    parts.append("Manbalar: " + "; ".join(
        f"{h['document_title']} (v{h['version_no']}, {h['locator']})" for h in hits[:MAX_QUOTES]))
    return "\n\n".join(parts + notes), True


def edit_candidates(edit: Edit, search: dict[str, Any]) -> list[dict[str, Any]]:
    needle = _norm(edit.find)
    return [h for h in search["results"] if needle in _norm(h["text"])]


def count(haystack: str, needle: str) -> int:
    return _norm(haystack).count(_norm(needle))


def draft_arguments(hit: dict[str, Any], section_id: str, edit: Edit) -> dict[str, Any]:
    return {"document_id": hit["document_id"], "base_version_id": hit["version_id"],
            "expected_version_id": hit["version_id"],
            "operations": [{"op": "replace_text", "section_id": section_id, "find": edit.find,
                            "replace": edit.replace, "occurrence": 1}],
            "comment": f"AI taklifi: “{edit.find}” → “{edit.replace}”"[:500]}


def draft_answer(draft: dict[str, Any], hit: dict[str, Any]) -> str:
    lines = [f"*{hit['document_title']}* uchun yangi draft versiya yaratildi "
             f"(v{draft['version_no']}). Joriy versiya o‘zgarmadi.", "", "O‘zgarishlar:"]
    for c in draft["changes"][:10]:
        lines.append(f"- {c['locator']}: “{c['before'] or ''}” → “{c['after'] or ''}”")
    lines += ["", "Tekshirib, Hujjatlar sahifasida “Joriy qilish” tugmasi bilan tasdiqlang."]
    lines += [f"Ogohlantirish: {w}" for w in draft.get("warnings", [])]
    return "\n".join(lines)


def ambiguity_question(edit: Edit, hits: list[dict[str, Any]]) -> str:
    places = "; ".join(f"{h['document_title']} v{h['version_no']}, {h['locator']}"
                       for h in hits[:5])
    return (f"“{edit.find}” bir nechta joyda uchradi: {places}. Qaysi birini o‘zgartiray? "
            "Hujjatni tanlab (chip) yoki joyini aniq yozib qayta yuboring.")
