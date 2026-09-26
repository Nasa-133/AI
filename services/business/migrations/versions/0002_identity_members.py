"""Identity: takliflar, parol tiklash, TOTP replay himoyasi.

Revision ID: 0002
Revises: 0001
"""

import os

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("BUSINESS_APP_ROLE", "business_app")


def upgrade() -> None:
    op.execute("ALTER TABLE identity.users ADD COLUMN mfa_last_used_step bigint")

    op.execute("""
        CREATE TABLE identity.invitations (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES identity.tenants(id) ON DELETE CASCADE,
            email text NOT NULL,
            role text NOT NULL CHECK (role IN ('owner', 'admin', 'analyst', 'viewer')),
            token_hash text NOT NULL UNIQUE,
            invited_by uuid NOT NULL REFERENCES identity.users(id),
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL,
            accepted_at timestamptz
        )
    """)
    op.execute("CREATE INDEX invitations_tenant_idx ON identity.invitations (tenant_id)")
    # Taklif tenant ma’lumoti: odatda joriy tenant bo‘yicha ko‘rinadi. Qabul qilishda tenant
    # hali ma’lum emas — faqat aynan shu token hash’li satr ochiladi.
    op.execute("ALTER TABLE identity.invitations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identity.invitations FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY invitations_access ON identity.invitations
        USING (tenant_id = platform.current_tenant_id()
               OR token_hash = NULLIF(current_setting('app.invitation_token_hash', true), ''))
        WITH CHECK (tenant_id = platform.current_tenant_id())
    """)

    # Foydalanuvchi darajasidagi (global) token, sessions kabi hash bo‘yicha qidiriladi.
    op.execute("""
        CREATE TABLE identity.password_reset_tokens (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
            token_hash text NOT NULL UNIQUE,
            created_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL,
            used_at timestamptz
        )
    """)

    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON identity.invitations,"
        f" identity.password_reset_tokens TO {APP_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP TABLE identity.password_reset_tokens")
    op.execute("DROP TABLE identity.invitations")
    op.execute("ALTER TABLE identity.users DROP COLUMN mfa_last_used_step")
