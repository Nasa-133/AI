from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from ..domain.spec import DashboardSpec


@dataclass(frozen=True, slots=True)
class DashboardRecord:
    id: UUID
    version: int
    spec: dict[str, Any]
    created_by: UUID
    updated_at: datetime


class DashboardStore(Protocol):
    async def create(self, dashboard_id: UUID, spec: DashboardSpec, *, user_id: UUID,
                     task_id: UUID | None) -> DashboardRecord: ...
    async def get(self, dashboard_id: UUID) -> DashboardRecord | None: ...
    async def list(self, *, limit: int, query: str | None) -> list[DashboardRecord]: ...


class QueryResults(Protocol):
    async def result(self, query_id: UUID) -> dict[str, Any] | None: ...
