"""Dashboards: versiyali spec (widget’lar query_spec_id’ga bog‘langan).

Revision ID: 0007
Revises: 0006
"""

from alembic import op
from rls import grant_schema, tenant_rls  # type: ignore[import-not-found]

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA dashboards")
    op.execute("""
        CREATE TABLE dashboards.dashboards (
            tenant_id uuid NOT NULL, id uuid NOT NULL, title text NOT NULL, description text,
            current_version integer NOT NULL, created_by uuid NOT NULL, created_task_id uuid,
            created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE dashboards.dashboard_versions (
            tenant_id uuid NOT NULL, dashboard_id uuid NOT NULL, version integer NOT NULL,
            spec jsonb NOT NULL, created_by uuid NOT NULL, created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, dashboard_id, version),
            FOREIGN KEY (tenant_id, dashboard_id) REFERENCES dashboards.dashboards (tenant_id, id)
        )
    """)
    for t in ("dashboards", "dashboard_versions"):
        tenant_rls(f"dashboards.{t}")
    grant_schema("dashboards")


def downgrade() -> None:
    op.execute("DROP SCHEMA dashboards CASCADE")
