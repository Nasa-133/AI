"""Strukturali patch (TZ 9.4): faqat ko‘rsatilgan bo‘limdagi aniq matn o‘zgaradi.

Nishon noaniq bo‘lsa (matn bo‘limda so‘ralgandan kam uchrasa) — rad etiladi: agent
aniqlashtirishi kerak. So‘ralmagan summa/sana/majburiyat o‘zgarmaydi — faqat `find` almashadi.
"""

import difflib
from dataclasses import dataclass
from enum import StrEnum

from business.kernel.errors import BusinessError, ValidationFailed

from .structure import Section


class PatchTargetInvalid(ValidationFailed):
    code = "PATCH_TARGET_INVALID"


class VersionConflict(BusinessError):
    code = "VERSION_CONFLICT"


@dataclass(frozen=True, slots=True)
class ReplaceText:
    section_id: str
    find: str
    replace: str
    occurrence: int = 1


class ChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class Change:
    section_id: str
    locator: str
    change: ChangeKind
    before: str | None
    after: str | None


def validate(ops: list[ReplaceText], sections: list[Section]) -> None:
    by_id = {s.section_id: s for s in sections}
    for op in ops:
        section = by_id.get(op.section_id)
        if section is None:
            raise PatchTargetInvalid(f"Bo‘lim topilmadi: {op.section_id}")
        found = section.text.count(op.find)
        if found < op.occurrence:
            raise PatchTargetInvalid(
                f"{section.locator}: “{op.find}” {op.occurrence}-marta uchramaydi "
                f"(topildi: {found}). Aniqroq matn yoki bo‘limni ko‘rsating.")
        if op.find == op.replace:
            raise PatchTargetInvalid("O‘zgartirish bo‘sh: eski va yangi matn bir xil.")


def replace_nth(text: str, find: str, replace: str, occurrence: int) -> str:
    start = -1
    for _ in range(occurrence):
        start = text.find(find, start + 1)
    return text[:start] + replace + text[start + len(find):]


def apply(ops: list[ReplaceText], sections: list[Section]) -> list[Section]:
    """Yangi bo‘limlar ro‘yxati; asl ro‘yxat o‘zgarmaydi."""
    validate(ops, sections)
    texts = {s.section_id: s.text for s in sections}
    for op in ops:
        texts[op.section_id] = replace_nth(texts[op.section_id], op.find, op.replace, op.occurrence)
    return [Section(s.section_id, s.ordinal, s.kind, s.locator, texts[s.section_id])
            for s in sections]


def diff(left: list[Section], right: list[Section]) -> tuple[list[Change], int]:
    """Bo‘lim darajasidagi farq: ID bo‘yicha moslanadi; tartibdagi o‘zgarishlar ham ko‘rinadi."""
    lmap = {s.section_id: s for s in left}
    rmap = {s.section_id: s for s in right}
    changes: list[Change] = []
    unchanged = 0
    for s in right:
        old = lmap.get(s.section_id)
        if old is None:
            changes.append(Change(s.section_id, s.locator, ChangeKind.ADDED, None, s.text))
        elif old.text != s.text:
            changes.append(Change(s.section_id, s.locator, ChangeKind.CHANGED, old.text, s.text))
        else:
            unchanged += 1
    changes += [Change(s.section_id, s.locator, ChangeKind.REMOVED, s.text, None)
                for s in left if s.section_id not in rmap]
    return changes, unchanged


def word_diff(before: str, after: str) -> list[tuple[str, str]]:
    """UI uchun so‘z darajasidagi farq: ("=", matn) | ("-", o‘chgan) | ("+", qo‘shilgan)."""
    a, b = before.split(" "), after.split(" ")
    out: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.append(("=", " ".join(a[i1:i2])))
        if tag in ("delete", "replace"):
            out.append(("-", " ".join(a[i1:i2])))
        if tag in ("insert", "replace"):
            out.append(("+", " ".join(b[j1:j2])))
    return out


def ensure_current(current_version_id: object, expected_version_id: object) -> None:
    """Parallel tahrir: kutilgan versiya joriy bo‘lmasa yashirin overwrite yo‘q (D05)."""
    if current_version_id != expected_version_id:
        raise VersionConflict("Hujjat boshqa foydalanuvchi tomonidan o‘zgartirilgan. "
                              "Joriy versiyani ochib, o‘zgarishni qayta qo‘llang.")
