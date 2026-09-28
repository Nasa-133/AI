"""13.15 gate 6 / I06: runtime credential’lari faqat o‘z bazasiga kiradi; app roli RLS’ni
chetlab o‘ta olmaydi; tenant jadvallarida FORCE RLS."""

import asyncpg
import pytest

pytestmark = pytest.mark.integration

HOST = "postgresql://{user}:{password}@localhost:55432/{db}"
ROLES = {
    "business_app": ("business_app_dev", "business"),
    "ai_app": ("ai_app_dev", "ai_runtime"),
    "integration_app": ("integration_app_dev", "integration_runtime"),
}


@pytest.mark.parametrize("role", list(ROLES))
@pytest.mark.parametrize("foreign", ["business", "ai_runtime", "integration_runtime"])
async def test_runtime_credential_cannot_open_foreign_database(role: str, foreign: str) -> None:
    password, own = ROLES[role]
    if foreign == own:
        conn = await asyncpg.connect(HOST.format(user=role, password=password, db=own))
        await conn.close()
        return
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await asyncpg.connect(HOST.format(user=role, password=password, db=foreign))


@pytest.mark.parametrize("role", list(ROLES))
async def test_app_role_is_not_privileged(role: str) -> None:
    password, db = ROLES[role]
    conn = await asyncpg.connect(HOST.format(user=role, password=password, db=db))
    try:
        row = await conn.fetchrow("SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb"
                                  " FROM pg_roles WHERE rolname = current_user")
        assert not any(row.values()), dict(row)
        owned = await conn.fetchval(
            "SELECT count(*) FROM pg_tables WHERE tableowner = current_user"
            " AND schemaname NOT IN ('pg_catalog', 'information_schema')")
        assert owned == 0  # jadval egasi migratsiya roli; app roli emas
    finally:
        await conn.close()


# Ongli istisnolar (yangi jadval bu ro‘yxatga faqat review bilan qo‘shiladi):
RLS_EXEMPT = {
    # Sessiya token xeshi bo‘yicha tenant ma’lum bo‘lishidan oldin topiladi (autentifikatsiya).
    "identity.sessions": "tenant hali noma’lum — token xeshi bo‘yicha qidiruv",
    # Outbox relay barcha tenantlar eventlarini broker’ga uzatadi (transport, TZ 13.8).
    "messaging.outbox": "relay tenantlararo transport",
}


async def test_every_tenant_table_forces_rls() -> None:
    conn = await asyncpg.connect(HOST.format(user="business_app", password="business_app_dev",
                                             db="business"))
    try:
        rows = await conn.fetch("""
            SELECT c.relnamespace::regnamespace::text AS schema, c.relname, c.relrowsecurity,
                   c.relforcerowsecurity
            FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE c.relkind = 'r' AND a.attname = 'tenant_id' AND NOT a.attisdropped
              AND c.relnamespace::regnamespace::text NOT IN ('pg_catalog', 'information_schema')
        """)
        assert len(rows) > 20
        weak = [f"{r['schema']}.{r['relname']}" for r in rows
                if not (r["relrowsecurity"] and r["relforcerowsecurity"])
                and f"{r['schema']}.{r['relname']}" not in RLS_EXEMPT]
        assert weak == [], f"FORCE RLS yo‘q: {weak}"
    finally:
        await conn.close()
