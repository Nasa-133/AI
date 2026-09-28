"""Identity kontekstining boshqa kontekstlar uchun ochiq kontrakti.

Boshqa kontekstlar faqat shu moduldan import qiladi (tests/architecture tekshiradi).
"""

from typing import Protocol
from uuid import UUID

from .application.dto import AuthContext, TenantProfile
from .domain.model import Role


class TenantDirectory(Protocol):
    """Boshqa kontekstlar Identity’dan faqat shu port orqali o‘qiydi."""

    async def tenant_profile(self, tenant_id: UUID) -> TenantProfile: ...
    async def role_of(self, tenant_id: UUID, user_id: UUID) -> Role | None: ...
    async def branch_scope_of(self, tenant_id: UUID, user_id: UUID) -> tuple[str, ...] | None:
        """S02: None — barcha filiallar."""
        ...


__all__ = ["AuthContext", "Role", "TenantDirectory", "TenantProfile"]
