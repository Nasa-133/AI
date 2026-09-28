"""Psevdonimlash (TZ 13.12): tenant sozlamasi va vazifa bo‘yicha token → asl qiymat (shifrlangan).

Revision ID: 0015
Revises: 0014
"""

from alembic import op
from rls import grant_schema, tenant_rls  # type: ignore[import-not-found]

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE governance.privacy_settings (
            tenant_id uuid PRIMARY KEY,
            pseudonymize boolean NOT NULL DEFAULT true,
            mask_customer_names boolean NOT NULL DEFAULT true,
            updated_by uuid, updated_at timestamptz NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE governance.pii_tokens (
            tenant_id uuid NOT NULL, task_id uuid NOT NULL, token text NOT NULL,
            value_enc text NOT NULL, created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, task_id, token)
        )
    """)
    for t in ("privacy_settings", "pii_tokens"):
        tenant_rls(f"governance.{t}")
    grant_schema("governance")
    # Audit — faqat qo‘shiladi (grant_schema barcha huquqni qayta bergan bo‘lishi mumkin).
    from rls import APP_ROLE  # type: ignore[import-not-found]
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON governance.audit_events FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE governance.pii_tokens")
    op.execute("DROP TABLE governance.privacy_settings")
