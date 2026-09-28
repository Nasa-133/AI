"""Hujjat ACL (TZ 3, 9): kim ko‘radi, kim draft yaratadi, kim asosiy versiya qiladi."""

from dataclasses import dataclass
from uuid import UUID

from business.kernel.errors import BusinessError

MANAGERS = frozenset({"owner", "admin"})
EDITORS = frozenset({"owner", "admin", "analyst"})


class DocumentForbidden(BusinessError):
    code = "FORBIDDEN"


@dataclass(frozen=True, slots=True)
class Access:
    created_by: UUID
    visibility: str
    shared_with: frozenset[UUID]


def can_view(a: Access, user_id: UUID, role: str) -> bool:
    return (role in MANAGERS or a.created_by == user_id or a.visibility == "tenant"
            or user_id in a.shared_with)


def can_draft(a: Access, user_id: UUID, role: str) -> bool:
    return role in EDITORS and can_view(a, user_id, role)


def can_promote(a: Access, user_id: UUID, role: str) -> bool:
    """Asosiy versiyani almashtirish — alohida vakolat (TZ 9.4): egasi yoki rahbar."""
    return role in MANAGERS or (role in EDITORS and a.created_by == user_id)
