"""Identity & Access: foydalanuvchi, korxona, a’zolik, sessiya va tenant RLS.

Revision ID: 0001
Revises:
"""

import os

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("BUSINESS_APP_ROLE", "business_app")


def upgrade() -> None:
    # Tenant konteksti: tranzaksiya ichida set_config orqali o‘rnatiladi.
    op.execute("CREATE SCHEMA platform")
    op.execute("""
        CREATE FUNCTION platform.current_tenant_id() RETURNS uuid
        LANGUAGE sql STABLE AS
        $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$
    """)
    op.execute("""
        CREATE FUNCTION platform.current_user_id() RETURNS uuid
        LANGUAGE sql STABLE AS
        $$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$
    """)

    op.execute("CREATE SCHEMA identity")
    op.execute("""
        CREATE TABLE identity.users (
            id uuid PRIMARY KEY,
            email text NOT NULL UNIQUE,
            password_hash text NOT NULL,
            mfa_secret_encrypted text,
            mfa_enabled boolean NOT NULL DEFAULT false,
            failed_login_count integer NOT NULL DEFAULT 0,
            locked_until timestamptz,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE identity.tenants (
            id uuid PRIMARY KEY,
            name text NOT NULL,
            timezone text NOT NULL,
            base_currency char(3) NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE identity.memberships (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES identity.tenants(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
            role text NOT NULL CHECK (role IN ('owner', 'admin', 'analyst', 'viewer')),
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            UNIQUE (tenant_id, user_id)
        )
    """)
    op.execute("CREATE INDEX memberships_user_id_idx ON identity.memberships (user_id)")
    op.execute("""
        CREATE TABLE identity.sessions (
            id uuid PRIMARY KEY,
            token_hash text NOT NULL UNIQUE,
            user_id uuid NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
            tenant_id uuid NOT NULL REFERENCES identity.tenants(id) ON DELETE CASCADE,
            mfa_verified boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL
        )
    """)
    op.execute("CREATE INDEX sessions_user_id_idx ON identity.sessions (user_id)")
    op.execute("CREATE INDEX sessions_expires_at_idx ON identity.sessions (expires_at)")

    # RLS (TZ 13.12): app roli owner emas, FORCE bilan owner ham bo‘ysunadi.
    # memberships: joriy tenant a’zolari yoki foydalanuvchining o‘z a’zoliklari ko‘rinadi.
    op.execute("ALTER TABLE identity.memberships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identity.memberships FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY memberships_access ON identity.memberships
        USING (tenant_id = platform.current_tenant_id()
               OR user_id = platform.current_user_id())
        WITH CHECK (tenant_id = platform.current_tenant_id())
    """)
    # tenants: joriy tenant yoki foydalanuvchi a’zo bo‘lgan korxonalar.
    op.execute("ALTER TABLE identity.tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identity.tenants FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenants_access ON identity.tenants
        USING (id = platform.current_tenant_id()
               OR EXISTS (SELECT 1 FROM identity.memberships m
                          WHERE m.tenant_id = tenants.id
                            AND m.user_id = platform.current_user_id()))
        WITH CHECK (id = platform.current_tenant_id())
    """)
    # users va sessions global: login email/token hash bo‘yicha tenant kontekstisiz ishlaydi.

    op.execute(f"GRANT USAGE ON SCHEMA platform, identity TO {APP_ROLE}")
    op.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA platform TO {APP_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA identity TO {APP_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA identity CASCADE")
    op.execute("DROP SCHEMA platform CASCADE")
