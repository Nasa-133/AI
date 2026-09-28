"""Agent navbati va ofis holati (TZ 4, 6, 11): parallel limit, navbatdagi o‘rin, qadam turi.

`dispatched_at` NULL — vazifa agent navbatida (RunAgent hali yuborilmagan); `dispatch` — keyin
yuboriladigan buyruq ma’lumoti (token yuborish paytida beriladi). `title` — ofis kartasi uchun.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE workspace.tasks
            ADD COLUMN dispatched_at timestamptz,
            ADD COLUMN dispatch jsonb,
            ADD COLUMN title text NOT NULL DEFAULT ''
    """)
    op.execute("UPDATE workspace.tasks SET dispatched_at = created_at")
    op.execute("ALTER TABLE workspace.task_steps ADD COLUMN wait_reason text"
               " CHECK (wait_reason IN ('input', 'approval'))")
    op.execute("CREATE INDEX tasks_by_agent ON workspace.tasks"
               " (tenant_id, agent_role_key, status, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX workspace.tasks_by_agent")
    op.execute("ALTER TABLE workspace.task_steps DROP COLUMN wait_reason")
    op.execute("ALTER TABLE workspace.tasks DROP COLUMN dispatched_at, DROP COLUMN dispatch,"
               " DROP COLUMN title")
