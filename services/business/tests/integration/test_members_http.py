from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from business.platform.db import bind_request_context
from tests.unit.identity.fakes import RecordingNotifier

from .test_identity_http import PASSWORD, complete_mfa, csrf, new_client, onboard

pytestmark = pytest.mark.integration


async def test_invite_accept_and_manage_roles(client: httpx.AsyncClient,
                                              notifier: RecordingNotifier) -> None:
    email = f"analyst-{uuid4().hex[:8]}@demo.uz"
    async with new_client(client) as owner:
        _, body = await onboard(owner)
        await complete_mfa(owner)
        r = await owner.post("/api/v1/invitations", json={"email": email, "role": "analyst"},
                             headers=csrf(owner))
        assert r.status_code == 201, r.text
        assert [i["email"] for i in (await owner.get("/api/v1/invitations")).json()] == [email]
        token = next(t for e, t in notifier.invitations if e == email)

        async with new_client(client) as invited:
            r = await invited.post("/api/v1/invitations/accept",
                                   json={"token": token, "password": PASSWORD})
            assert r.status_code == 200, r.text
            assert r.json()["tenant_id"] == body["tenant_id"] and r.json()["role"] == "analyst"
            user_id = r.json()["user_id"]
            # Analyst a’zolarni boshqara olmaydi.
            assert (await invited.get("/api/v1/members")).status_code == 403

            r = await owner.patch(f"/api/v1/members/{user_id}", json={"role": "viewer"},
                                  headers=csrf(owner))
            assert r.status_code == 200 and r.json()["role"] == "viewer"
            r = await owner.delete(f"/api/v1/members/{user_id}", headers=csrf(owner))
            assert r.status_code == 204
            # Chiqarilgan a’zo sessiyasi darhol ishlamaydi.
            assert (await invited.get("/api/v1/me")).status_code == 401

        r = await owner.patch(f"/api/v1/members/{body['user_id']}", json={"role": "admin"},
                              headers=csrf(owner))
        assert r.status_code == 409 and r.json()["code"] == "LAST_OWNER"


async def test_password_reset_over_http(client: httpx.AsyncClient,
                                        notifier: RecordingNotifier) -> None:
    async with new_client(client) as c:
        email, _ = await onboard(c)
        r = await c.post("/api/v1/auth/password-reset", json={"email": email})
        assert r.status_code == 202
        token = next(t for e, t in reversed(notifier.resets) if e == email)
        r = await c.post("/api/v1/auth/password-reset/confirm",
                         json={"token": token, "new_password": "brand-new-password"})
        assert r.status_code == 204
        assert (await c.get("/api/v1/me")).status_code == 401  # sessiyalar yopildi
        r = await c.post("/api/v1/auth/password-reset/confirm",
                         json={"token": token, "new_password": "brand-new-password"})
        assert r.status_code == 410
        r = await c.post("/api/v1/auth/login",
                         json={"email": email, "password": "brand-new-password"})
        assert r.status_code == 200
    # Noma’lum email ham bir xil javob oladi (mavjudlik oshkor bo‘lmaydi).
    async with new_client(client) as c:
        r = await c.post("/api/v1/auth/password-reset", json={"email": "no-such@demo.uz"})
        assert r.status_code == 202


async def test_invitations_are_tenant_isolated_by_rls(
    client: httpx.AsyncClient, app_engine: AsyncEngine, notifier: RecordingNotifier
) -> None:
    async with new_client(client) as a, new_client(client) as b:
        _, body_a = await onboard(a, "A MChJ")
        await complete_mfa(a)
        await a.post("/api/v1/invitations",
                     json={"email": f"x-{uuid4().hex[:6]}@demo.uz", "role": "viewer"},
                     headers=csrf(a))
        _, body_b = await onboard(b, "B MChJ")

    async with app_engine.connect() as conn, conn.begin():
        await bind_request_context(conn, tenant_id=body_b["tenant_id"],
                                   user_id=body_b["user_id"])
        visible = (await conn.execute(text(
            "SELECT count(*) FROM identity.invitations WHERE tenant_id = :t"),
            {"t": body_a["tenant_id"]})).scalar()
        assert visible == 0
