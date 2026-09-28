"""Qidiruv normalizatori (TZ 9.2): indeksda ham, so‘rovda ham bir xil qo‘llanadi."""

import re
import unicodedata

# oʻ, o‘, o’, o', o` → o' ; gʻ ... → g' ; ajratuvchi tutuq belgilari → '
_APOSTROPHES = str.maketrans({c: "'" for c in "ʻʼ‘’`´ʹ′"})
_CYRILLIC = {
    "ш": "sh", "ч": "ch", "ў": "o'", "ғ": "g'", "ё": "yo", "ю": "yu", "я": "ya", "ц": "ts",
    "щ": "sh", "ж": "j", "х": "x", "ҳ": "h", "қ": "q", "й": "y", "ъ": "'", "ь": "",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "з": "z", "и": "i", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "э": "e", "ы": "i",
}
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Kichik harf, tutuq belgilari yagona, kirill → lotin, bo‘shliqlar yig‘ilgan."""
    t = unicodedata.normalize("NFC", text).lower().translate(_APOSTROPHES)
    t = "".join(_CYRILLIC.get(ch, ch) for ch in t)
    return _SPACES.sub(" ", t).strip()


def query_terms(query: str) -> list[str]:
    """FTS uchun so‘zlar (tutuq belgisi so‘z ichida qoladi: to'lov)."""
    return [w for w in re.findall(r"[\w']+", normalize(query)) if len(w.strip("'")) > 1]
