"""Dashboard ACL (TZ 3, 8.2): kim ko‘radi va tahrirlaydi. Har o‘qish va eksportda tekshiriladi."""

import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from business.kernel.errors import BusinessError

MANAGERS = frozenset({"owner", "admin"})


class Visibility(StrEnum):
    PRIVATE = "private"  # yaratuvchi, rahbarlar va aniq ulashilganlar
    TENANT = "tenant"  # korxonaning barcha a’zolari (Viewer ham)


class DashboardForbidden(BusinessError):
    code = "FORBIDDEN"


@dataclass(frozen=True, slots=True)
class Access:
    created_by: UUID
    visibility: Visibility
    shared_with: frozenset[UUID]


def can_view(access: Access, user_id: UUID, role: str) -> bool:
    return (role in MANAGERS or access.created_by == user_id
            or access.visibility is Visibility.TENANT or user_id in access.shared_with)


def can_edit(access: Access, user_id: UUID, role: str) -> bool:
    """Viewer hech qachon tahrirlamaydi; yaratuvchi va rahbarlar tahrirlaydi."""
    return role != "viewer" and (role in MANAGERS or access.created_by == user_id)


def within_branch_scope(scope: tuple[str, ...] | None, branches: tuple[str, ...] | None) -> bool:
    """S02: widget natijasi faqat ruxsat etilgan filiallar bilan cheklangan bo‘lsa ko‘rinadi.

    `branches` — widget so‘rovining amaldagi filial filtri (None — barcha filiallar).
    """
    if scope is None:
        return True
    return bool(branches) and set(branches or ()) <= set(scope)


_DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: str | None) -> str:
    """Excel/CSV formula injection’ni neytrallash (TZ 9.4). Oddiy sonlar o‘zgarmaydi."""
    if value is None:
        return ""
    if value.startswith(_FORMULA_START) and not _DECIMAL.fullmatch(value):
        return "'" + value
    return value
