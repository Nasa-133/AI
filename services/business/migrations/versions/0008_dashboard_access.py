"""Dashboard ko‘rinishi va ulashish (TZ 3 ACL, 8.2): private | tenant + aniq foydalanuvchilar.

Revision ID: 0008
Revises: 0007
"""

from alembic import op
from rls import grant_schema, tenant_rls  # type: ignore[import-not-found]

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Mavjud dashboardlar oldingi xatti-harakatni saqlaydi (hamma a’zoga ko‘rinadi).
    op.execute("""
        ALTER TABLE dashboards.dashboards ADD COLUMN visibility text NOT NULL DEFAULT 'tenant'
        CHECK (visibility IN ('private', 'tenant'))
    """)
    op.execute("""
        CREATE TABLE dashboards.dashboard_shares (
            tenant_id uuid NOT NULL, dashboard_id uuid NOT NULL, user_id uuid NOT NULL,
            created_by uuid NOT NULL, created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, dashboard_id, user_id),
            FOREIGN KEY (tenant_id, dashboard_id) REFERENCES dashboards.dashboards (tenant_id, id)
                ON DELETE CASCADE
        )
    """)
    tenant_rls("dashboards.dashboard_shares")
    grant_schema("dashboards")


def downgrade() -> None:
    op.execute("DROP TABLE dashboards.dashboard_shares")
    op.execute("ALTER TABLE dashboards.dashboards DROP COLUMN visibility")
