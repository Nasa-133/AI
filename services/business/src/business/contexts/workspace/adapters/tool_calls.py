"""Tool chaqiruvlari jurnali: (task_id, tool_call_id) bo‘yicha idempotentlik."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


class SqlToolCallLog:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._c = conn
        self._tenant = tenant_id

    async def get(self, task_id: UUID, tool_call_id: str) -> dict[str, Any] | None:
        r = (await self._c.execute(text(
            "SELECT result FROM workspace.tool_calls WHERE task_id = :task AND tool_call_id = :id"),
            {"task": task_id, "id": tool_call_id})).first()
        return None if r is None else dict(r.result)

    async def save(self, task_id: UUID, tool_call_id: str, tool: str,
                   result: dict[str, Any]) -> None:
        await self._c.execute(text(
            "INSERT INTO workspace.tool_calls (tenant_id, task_id, tool_call_id, tool_name, result,"
            " created_at) VALUES (:t, :task, :id, :tool, CAST(:r AS jsonb), now())"),
            {"t": self._tenant, "task": task_id, "id": tool_call_id, "tool": tool,
             "r": json.dumps(result, ensure_ascii=False)})
