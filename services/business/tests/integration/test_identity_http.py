from uuid import uuid4

import httpx
import pyotp
import pytest

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"


def new_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Alohida cookie jar bilan yangi “brauzer”."""
    return httpx.AsyncClient(transport=client._transport, base_url="http://test")


def csrf(c: httpx.AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("abo_csrf") or ""}


async def onboard(c: httpx.AsyncClient, name: str = "Demo MChJ") -> tuple[str, dict[str, object]]:
    email = f"owner-{uuid4().hex[:8]}@demo.uz"
    r = await c.post("/api/v1/tenants",
                     json={"email": email, "password": PASSWORD, "tenant_name": name})
    assert r.status_code == 201, r.text
    return email, r.json()


async def complete_mfa(c: httpx.AsyncClient) -> None:
    r = await c.post("/api/v1/auth/mfa/enroll", headers=csrf(c))
    assert r.status_code == 200, r.text
    code = pyotp.TOTP(r.json()["secret"]).now()
    r = await c.post("/api/v1/auth/mfa/verify", json={"code": code}, headers=csrf(c))
    assert r.status_code == 200, r.text
    assert r.json()["mfa_satisfied"] is True


async def test_health(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    assert (await client.get("/health/ready")).json()["db"] == "up"


async def test_owner_flow_with_mandatory_mfa(client: httpx.AsyncClient) -> None:
    async with new_client(client) as c:
        email, body = await onboard(c)
        assert body["role"] == "owner" and body["mfa_satisfied"] is False

        me = (await c.get("/api/v1/me")).json()
        assert me["email"] == email and me["mfa_satisfied"] is False

        # MFA tugallanmaguncha biznes endpointlari yopiq.
        r = await c.post("/api/v1/session/tenant", json={"tenant_id": body["tenant_id"]},
                         headers=csrf(c))
        assert r.status_code == 403 and r.json()["code"] == "MFA_REQUIRED"
        assert r.json()["trace_id"]

        await complete_mfa(c)
        r = await c.post("/api/v1/session/tenant", json={"tenant_id": body["tenant_id"]},
                         headers=csrf(c))
        assert r.status_code == 200, r.text


async def test_session_cookie_flags(client: httpx.AsyncClient) -> None:
    async with new_client(client) as c:
        r = await c.post("/api/v1/tenants", json={
            "email": f"owner-{uuid4().hex[:8]}@demo.uz", "password": PASSWORD,
            "tenant_name": "Cookie MChJ"})
        cookies = {h.split("=", 1)[0]: h.lower() for h in r.headers.get_list("set-cookie")}
        assert "httponly" in cookies["abo_session"] and "samesite=lax" in cookies["abo_session"]
        assert "httponly" not in cookies["abo_csrf"]  # frontend header’ga o‘qishi kerak


async def test_csrf_is_required_for_mutations_with_session(client: httpx.AsyncClient) -> None:
    async with new_client(client) as c:
        await onboard(c)
        r = await c.post("/api/v1/auth/mfa/enroll")
        assert r.status_code == 403 and r.json()["code"] == "CSRF_FAILED"


async def test_login_errors_follow_standard_format(client: httpx.AsyncClient) -> None:
    async with new_client(client) as c:
        email, _ = await onboard(c)
    async with new_client(client) as c:
        r = await c.post("/api/v1/auth/login", json={"email": email, "password": "bad-password"})
        assert r.status_code == 401
        assert set(r.json()) == {"code", "message", "retryable", "trace_id"}
        r = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200 and r.json()["mfa_satisfied"] is False


async def test_duplicate_onboarding_email_is_conflict(client: httpx.AsyncClient) -> None:
    async with new_client(client) as c:
        email, _ = await onboard(c)
    async with new_client(client) as c:
        r = await c.post("/api/v1/tenants",
                         json={"email": email, "password": PASSWORD, "tenant_name": "X MChJ"})
        assert r.status_code == 409 and r.json()["code"] == "EMAIL_TAKEN"


async def test_other_tenant_is_not_reachable(client: httpx.AsyncClient) -> None:
    async with new_client(client) as a, new_client(client) as b:
        _, body_a = await onboard(a, "A MChJ")
        _, body_b = await onboard(b, "B MChJ")
        await complete_mfa(a)
        r = await a.post("/api/v1/session/tenant", json={"tenant_id": body_b["tenant_id"]},
                         headers=csrf(a))
        # Mavjudlikni oshkor qilmaslik uchun 404 (TZ 15).
        assert r.status_code == 404
        me = (await a.get("/api/v1/me")).json()
        assert [m["tenant_id"] for m in me["memberships"]] == [body_a["tenant_id"]]


async def test_logout_revokes_session(client: httpx.AsyncClient) -> None:
    async with new_client(client) as c:
        await onboard(c)
        r = await c.post("/api/v1/auth/logout", headers=csrf(c))
        assert r.status_code == 204
    async with new_client(client) as c:
        assert (await c.get("/api/v1/me")).status_code == 401


async def test_owner_adds_second_company_and_switches(client: httpx.AsyncClient) -> None:
    async with new_client(client) as c:
        _, body = await onboard(c, "Asosiy MChJ")
        await complete_mfa(c)
        r = await c.post("/api/v1/tenants/additional", headers=csrf(c),
                         json={"tenant_name": "Test korxona"})
        assert r.status_code == 201, r.text
        second = r.json()["tenant_id"]
        me = (await c.get("/api/v1/me")).json()
        assert {m["tenant_name"]: m["role"] for m in me["memberships"]} == {
            "Asosiy MChJ": "owner", "Test korxona": "owner"}
        assert me["current_tenant_id"] == body["tenant_id"]  # joriy korxona o‘zgarmaydi
        switched = await c.post("/api/v1/session/tenant", headers=csrf(c),
                                json={"tenant_id": second})
        assert switched.status_code == 200 and switched.json()["tenant_id"] == second
        assert (await c.get("/api/v1/dashboards")).json() == []  # ma’lumot alohida
