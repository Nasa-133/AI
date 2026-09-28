"""Tenant ofis SSE: o‘zgarish belgisi (oxirgi event, oxirgi task yangilanishi) uchun indekslar.

Revision ID: 0016
Revises: 0015
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX task_events_by_tenant ON workspace.task_events (tenant_id, id DESC)")
    op.execute("CREATE INDEX tasks_by_update ON workspace.tasks (tenant_id, updated_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX workspace.tasks_by_update")
    op.execute("DROP INDEX workspace.task_events_by_tenant")
