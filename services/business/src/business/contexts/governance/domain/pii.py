"""Shaxsiy ma’lumotlarni psevdonimlash (TZ 13.12, 18): model kontekstiga ketishdan oldin Core’da.

Matndan topiladi: telefon, email, PINFL, pasport, bank kartasi. Jadval natijalarida — mijoz
ustunlari (tenant sozlamasi). Token deterministik (bir vazifa ichida bir qiymat — bir token),
shuning uchun model “bir xil mijoz”ni taniy oladi, lekin asl qiymatni ko‘rmaydi. Javob va tool
argumentlaridagi tokenlar Core’da asl qiymatga qaytariladi.
"""

import re
from collections.abc import Callable
from typing import Any

TokenFor = Callable[[str, str], str]  # (tur, qiymat) → token
Lookup = Callable[[str], str | None]  # token → asl qiymat

# Tartib muhim: uzunroq raqamli naqshlar oldin (karta 16 > PINFL 14 > telefon).
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("KARTA", re.compile(r"(?<!\d)(?:\d{4}[ -]?){3}\d{4}(?!\d)")),
    ("PINFL", re.compile(r"(?<!\d)[3-6]\d{13}(?!\d)")),
    ("PASPORT", re.compile(r"(?<![A-Za-z])[A-Z]{2}\s?\d{7}(?!\d)")),
    # Summa emas: oldidan/ortidan raqam, nuqta-vergul bilan kasr qismi kelmaydi.
    ("TEL", re.compile(r"(?<![\w+.,])(?:\+?998[\s-]?)?\(?(?:[3-9]\d)\)?[\s-]?\d{3}[\s-]?\d{2}"
                       r"[\s-]?\d{2}(?![\d]|[.,]\d)")),
]
TOKEN_RE = re.compile(r"\[(?:EMAIL|KARTA|PINFL|PASPORT|TEL|SHAXS)-[0-9a-f]{8}\]")
# Jadval natijasida shaxs nomi bo‘lishi mumkin bo‘lgan ustunlar.
PERSON_COLUMNS = frozenset({"customer", "customer_name", "full_name", "fio", "contact_name"})


# Summa (kasr qismi bilan) yoki qisqa son — shaxsiy ma’lumot emas; uzun butun son (PINFL,
# karta, telefon) esa tekshiriladi.
_DECIMAL = re.compile(r"^-?(?:\d+\.\d+|\d{1,8})$")


# UUID (snapshot, versiya, query ID’lari) shaxsiy ma’lumot emas; uning faqat raqamli qismlari
# karta/telefon naqshiga tushib qolmasligi uchun UUID’lar psevdonimlashdan butunlay chetda.
_UUID = re.compile(r"([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})")


def mask_text(text: str, token_for: TokenFor) -> str:
    if _DECIMAL.match(text):
        return text
    parts = _UUID.split(text)  # toq indekslar — UUID’lar
    for i in range(0, len(parts), 2):
        for kind, pattern in PATTERNS:
            parts[i] = pattern.sub(_replacer(kind, token_for), parts[i])
    return "".join(parts)


def _replacer(kind: str, token_for: TokenFor) -> Callable[[re.Match[str]], str]:
    return lambda m: token_for(kind, m.group(0))


def unmask_text(text: str, lookup: Lookup) -> str:
    return TOKEN_RE.sub(lambda m: lookup(m.group(0)) or m.group(0), text)


def mask_value(value: Any, token_for: TokenFor, *, mask_people: bool) -> Any:
    """Istalgan JSON qiymat: satrlar matn sifatida; `columns`+`rows` jadvalida shaxs ustunlari."""
    if isinstance(value, str):
        return mask_text(value, token_for)
    if isinstance(value, list):
        return [mask_value(v, token_for, mask_people=mask_people) for v in value]
    if not isinstance(value, dict):
        return value
    out = {k: mask_value(v, token_for, mask_people=mask_people) for k, v in value.items()}
    columns, rows = value.get("columns"), value.get("rows")
    if mask_people and isinstance(columns, list) and isinstance(rows, list):
        people = [i for i, c in enumerate(columns)
                  if isinstance(c, dict) and c.get("name") in PERSON_COLUMNS]
        if people:
            out["rows"] = [[token_for("SHAXS", str(cell)) if i in people and cell is not None
                            else mask_value(cell, token_for, mask_people=mask_people)
                            for i, cell in enumerate(row)] if isinstance(row, list) else row
                           for row in rows]
    return out


def unmask_value(value: Any, lookup: Lookup) -> Any:
    if isinstance(value, str):
        return unmask_text(value, lookup)
    if isinstance(value, list):
        return [unmask_value(v, lookup) for v in value]
    if isinstance(value, dict):
        return {k: unmask_value(v, lookup) for k, v in value.items()}
    return value


def redact_text(text: str) -> str:
    """Tiklanmaydigan yashirish (embedding uchun): qiymat o‘rniga faqat tur."""
    for kind, pattern in PATTERNS:
        text = pattern.sub(f"[{kind}]", text)
    return text
