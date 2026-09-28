from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from ..domain.access import Access, Visibility
from ..domain.spec import DashboardSpec


@dataclass(frozen=True, slots=True)
class DashboardRecord:
    id: UUID
    version: int
    spec: dict[str, Any]
    created_by: UUID
    updated_at: datetime
    visibility: Visibility = Visibility.TENANT
    shared_with: frozenset[UUID] = frozenset()

    @property
    def access(self) -> Access:
        return Access(self.created_by, self.visibility, self.shared_with)


@dataclass(frozen=True, slots=True)
class VersionInfo:
    version: int
    created_by: UUID
    created_at: datetime
    title: str


class DashboardStore(Protocol):
    async def create(self, dashboard_id: UUID, spec: DashboardSpec, *, user_id: UUID,
                     task_id: UUID | None) -> DashboardRecord: ...
    async def get(self, dashboard_id: UUID) -> DashboardRecord | None: ...
    async def list_visible(self, *, limit: int, query: str | None, user_id: UUID,
                   see_all: bool) -> list[DashboardRecord]:
        """Faqat foydalanuvchi ko‘ra oladiganlar (SQL darajasida filtrlangan)."""
        ...
    async def add_version(self, dashboard_id: UUID, spec: DashboardSpec, *,
                          user_id: UUID) -> DashboardRecord: ...
    async def versions(self, dashboard_id: UUID) -> list[VersionInfo]: ...
    async def set_access(self, dashboard_id: UUID, visibility: Visibility,
                         shared_with: frozenset[UUID], *, user_id: UUID) -> None: ...


class QueryResults(Protocol):
    async def result(self, query_id: UUID) -> dict[str, Any] | None: ...
    async def spec(self, query_id: UUID) -> dict[str, Any] | None:
        """Natijani yaratgan so‘rov argumentlari (drill-down keyingi darajasi uchun)."""
        ...


class QueryRefresher(Protocol):
    async def rerun(self, query_id: UUID) -> UUID | None:
        """Saqlangan so‘rovni oxirgi snapshot bilan qayta hisoblaydi; yangi query ID yoki None."""
        ...
