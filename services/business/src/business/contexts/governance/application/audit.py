"""Audit jurnali: yozish (entrypoint’lar), o‘qish (faqat egasi va administrator)."""

from typing import Any, Protocol
from uuid import UUID

from business.kernel.errors import BusinessError

READERS = frozenset({"owner", "admin"})


class AuditForbidden(BusinessError):
    code = "FORBIDDEN"


class AuditLog(Protocol):
    async def recent(self, limit: int, before_id: int | None) -> list[dict[str, Any]]: ...


async def read_audit(log: AuditLog, role: str, *, limit: int,
                     before_id: int | None) -> list[dict[str, Any]]:
    if role not in READERS:
        raise AuditForbidden("Audit jurnalini faqat korxona egasi va administrator ko‘radi.")
    rows = await log.recent(min(max(limit, 1), 200), before_id)
    return [{**r, "actor_id": str(r["actor_id"]) if isinstance(r["actor_id"], UUID) else None,
             "created_at": r["created_at"].isoformat()} for r in rows]
