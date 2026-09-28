"""Governance: AI budjeti (TZ 19): kundalik/oylik limit, vazifa bo‘yicha rezerv va haqiqiy sarf.

Revision ID: 0012
Revises: 0011
"""

from alembic import op
from rls import grant_schema, tenant_rls  # type: ignore[import-not-found]

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA governance")
    op.execute("""
        CREATE TABLE governance.budgets (
            tenant_id uuid PRIMARY KEY, currency char(3) NOT NULL DEFAULT 'USD',
            daily_limit numeric(14, 6) CHECK (daily_limit >= 0),
            monthly_limit numeric(14, 6) CHECK (monthly_limit >= 0),
            updated_by uuid, updated_at timestamptz NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE governance.budget_usage (
            tenant_id uuid NOT NULL, task_id uuid NOT NULL, reservation_id uuid NOT NULL,
            reserved numeric(14, 6) NOT NULL, actual numeric(14, 6),
            input_tokens bigint NOT NULL DEFAULT 0, output_tokens bigint NOT NULL DEFAULT 0,
            status text NOT NULL CHECK (status IN ('reserved', 'settled', 'released')),
            created_at timestamptz NOT NULL, settled_at timestamptz,
            PRIMARY KEY (tenant_id, task_id)
        )
    """)
    op.execute("CREATE INDEX budget_usage_by_time ON governance.budget_usage (tenant_id, created_at)")
    for t in ("budgets", "budget_usage"):
        tenant_rls(f"governance.{t}")
    grant_schema("governance")


def downgrade() -> None:
    op.execute("DROP SCHEMA governance CASCADE")
