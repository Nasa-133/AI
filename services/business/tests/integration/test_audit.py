"""Audit jurnali: muhim amallar yoziladi, faqat egasi/admin o‘qiydi, o‘zgartirib bo‘lmaydi."""

from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from business.platform.db import tenant_transaction
from tests.unit.documents.samples import make_docx
from tests.unit.identity.fakes import RecordingNotifier

from .test_documents import owner, upload
from .test_identity_http import PASSWORD, csrf, new_client

pytestmark = pytest.mark.integration


async def test_actions_are_audited_and_readable_by_owner_only(
        client: httpx.AsyncClient, notifier: RecordingNotifier, tmp_path: Path) -> None:
    async with owner(client, "Audit MChJ") as (c, _), new_client(client) as analyst:
        doc = await upload(c, make_docx(tmp_path / "A.docx"))
        await c.put("/api/v1/budget", headers=csrf(c), json={"monthly_limit": "20"})
        bad = await c.post(f"/api/v1/documents/{uuid4()}/promote", headers=csrf(c),
                           json={"version_id": str(uuid4()),
                                 "expected_current_version_id": str(uuid4())})
        assert bad.status_code == 404  # muvaffaqiyatsiz amal yozilmaydi

        email = f"a-{uuid4().hex[:6]}@demo.uz"
        await c.post("/api/v1/invitations", headers=csrf(c), json={"email": email,
                                                                   "role": "analyst"})
        token = next(t for e, t in notifier.invitations if e == email)
        await analyst.post("/api/v1/invitations/accept", json={"token": token,
                                                               "password": PASSWORD})

        events = (await c.get("/api/v1/audit")).json()
        actions = [e["action"] for e in events]
        for expected in ("tenant.created", "auth.mfa_verified", "document.uploaded",
                         "budget.updated", "member.invited", "member.joined"):
            assert expected in actions, actions
        assert "document.promoted" not in actions
        upload_event = next(e for e in events if e["action"] == "document.uploaded")
        assert upload_event["actor_kind"] == "user" and upload_event["ip"]
        assert "A.docx" not in str(events)  # fayl nomi/matni yozilmaydi — faqat ID’lar
        assert doc["id"]

        denied = await analyst.get("/api/v1/audit")
        assert denied.status_code == 403
        page = (await c.get("/api/v1/audit", params={"limit": 2})).json()
        older = (await c.get("/api/v1/audit", params={"before": page[-1]["id"]})).json()
        assert len(page) == 2 and all(e["id"] < page[-1]["id"] for e in older)


async def test_audit_is_append_only_and_purged_after_retention(
        client: httpx.AsyncClient, app_engine: AsyncEngine) -> None:
    async with owner(client, "Audit2 MChJ") as (_, tenant):
        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=None) as conn:
            await conn.execute(text(
                "INSERT INTO governance.audit_events (tenant_id, actor_kind, action, created_at)"
                " VALUES (:t, 'system', 'old.event', now() - interval '400 days')"), {"t": tenant})
        for statement in ("UPDATE governance.audit_events SET action = 'x'",
                          "DELETE FROM governance.audit_events"):
            with pytest.raises(DBAPIError, match="permission denied"):
                async with tenant_transaction(app_engine, tenant_id=tenant, user_id=None) as conn:
                    await conn.execute(text(statement))
        async with tenant_transaction(app_engine, tenant_id=tenant, user_id=None) as conn:
            removed = (await conn.execute(text("SELECT governance.purge_audit(365)"))).scalar_one()
            left = (await conn.execute(text(
                "SELECT count(*) FROM governance.audit_events"))).scalar_one()
        assert removed == 1 and left >= 1  # faqat muddati o‘tgan o‘chdi
        assert isinstance(tenant, UUID)
