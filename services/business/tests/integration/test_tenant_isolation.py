"""TZ 13.12 va S01: RLS, app roli huquqlari va tenant kontekstining pool orqali sizmasligi."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from business.platform.db import bind_request_context

pytestmark = pytest.mark.integration


async def _seed_tenant(conn: AsyncConnection) -> tuple[UUID, UUID]:
    tenant_id, user_id, now = uuid4(), uuid4(), datetime.now(UTC)
    await bind_request_context(conn, tenant_id=tenant_id, user_id=user_id)
    await conn.execute(
        text("INSERT INTO identity.users (id, email, password_hash, created_at, updated_at)"
             " VALUES (:id, :email, 'x', :now, :now)"),
        {"id": user_id, "email": f"{user_id.hex}@t.uz", "now": now},
    )
    await conn.execute(
        text("INSERT INTO identity.tenants VALUES (:id, 'T', 'Asia/Tashkent', 'UZS', :now, :now)"),
        {"id": tenant_id, "now": now},
    )
    await conn.execute(
        text("INSERT INTO identity.memberships VALUES (:id, :t, :u, 'owner', :now, :now)"),
        {"id": uuid4(), "t": tenant_id, "u": user_id, "now": now},
    )
    return tenant_id, user_id


async def test_app_role_cannot_bypass_rls(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ))).one()
        assert row == (False, False)
        owners = (await conn.execute(text(
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'identity'"
            " AND tableowner = current_user"
        ))).scalar_one()
        assert owners == 0


async def test_rls_hides_other_tenants(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        async with conn.begin():
            tenant_a, user_a = await _seed_tenant(conn)
        async with conn.begin():
            tenant_b, _ = await _seed_tenant(conn)

        async with conn.begin():
            await bind_request_context(conn, tenant_id=tenant_a, user_id=user_a)
            tenants = (await conn.execute(text("SELECT id FROM identity.tenants"))).scalars().all()
            members = (await conn.execute(
                text("SELECT tenant_id FROM identity.memberships"))).scalars().all()
            assert tenant_b not in tenants and tenant_a in tenants
            assert set(members) == {tenant_a}

        async with conn.begin():
            # Kontekstsiz so‘rov hech qanday tenant satrini ko‘rmaydi.
            await bind_request_context(conn, tenant_id=None, user_id=None)
            count = (await conn.execute(text("SELECT count(*) FROM identity.tenants"))).scalar()
            assert count == 0


async def test_cannot_insert_into_foreign_tenant(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        async with conn.begin():
            tenant_a, user_a = await _seed_tenant(conn)
        async with conn.begin():
            tenant_b, _ = await _seed_tenant(conn)
        with pytest.raises(Exception, match="row-level security"):
            async with conn.begin():
                await bind_request_context(conn, tenant_id=tenant_a, user_id=user_a)
                await conn.execute(
                    text("INSERT INTO identity.memberships"
                         " VALUES (:id, :t, :u, 'viewer', now(), now())"),
                    {"id": uuid4(), "t": tenant_b, "u": user_a},
                )


async def test_tenant_context_does_not_leak_between_transactions(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.connect() as conn:
        async with conn.begin():
            await bind_request_context(conn, tenant_id=uuid4(), user_id=uuid4())
        async with conn.begin():
            value = (await conn.execute(
                text("SELECT current_setting('app.tenant_id', true)"))).scalar()
            assert value in (None, "")
