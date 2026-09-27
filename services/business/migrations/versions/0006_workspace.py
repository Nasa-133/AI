"""Workspace: suhbat, xabar, task, qadam, SSE eventlari, tool chaqiruvlari, idempotentlik.

Revision ID: 0006
Revises: 0005
"""

from alembic import op
from rls import grant_schema, tenant_rls  # type: ignore[import-not-found]

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA workspace")
    op.execute("""
        CREATE TABLE workspace.conversations (
            tenant_id uuid NOT NULL, id uuid NOT NULL, title text NOT NULL, created_by uuid NOT NULL,
            created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE workspace.tasks (
            tenant_id uuid NOT NULL, id uuid NOT NULL, conversation_id uuid NOT NULL,
            initiator_id uuid NOT NULL, agent_role_key text NOT NULL,
            status text NOT NULL CHECK (status IN ('queued', 'running', 'awaiting_input',
                'awaiting_approval', 'succeeded', 'partial', 'failed', 'cancelled')),
            cancel_requested boolean NOT NULL DEFAULT false,
            error_code text, limitations jsonb NOT NULL DEFAULT '[]',
            created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id),
            FOREIGN KEY (tenant_id, conversation_id) REFERENCES workspace.conversations (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE workspace.messages (
            tenant_id uuid NOT NULL, id uuid NOT NULL, conversation_id uuid NOT NULL,
            author_kind text NOT NULL CHECK (author_kind IN ('user', 'agent')),
            author_id uuid, agent_role_key text, content text NOT NULL,
            task_id uuid, structured jsonb, source_refs jsonb NOT NULL DEFAULT '[]',
            created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id),
            FOREIGN KEY (tenant_id, conversation_id) REFERENCES workspace.conversations (tenant_id, id)
        )
    """)
    op.execute("CREATE INDEX messages_by_conversation ON workspace.messages (tenant_id, conversation_id, created_at)")
    op.execute("""
        CREATE TABLE workspace.task_steps (
            tenant_id uuid NOT NULL, id uuid NOT NULL, task_id uuid NOT NULL,
            agent_role_key text NOT NULL, kind text NOT NULL,
            status text NOT NULL CHECK (status IN ('pending', 'running', 'waiting', 'succeeded',
                'failed', 'skipped', 'cancelled')),
            phase text, agent_run_id uuid, progress_seq integer NOT NULL DEFAULT -1,
            created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id),
            FOREIGN KEY (tenant_id, task_id) REFERENCES workspace.tasks (tenant_id, id)
        )
    """)
    # SSE: global monoton `id` — Last-Event-ID sifatida ishlatiladi (TZ 13.9).
    op.execute("""
        CREATE TABLE workspace.task_events (
            id bigserial PRIMARY KEY, tenant_id uuid NOT NULL, task_id uuid NOT NULL,
            event_type text NOT NULL, payload jsonb NOT NULL, created_at timestamptz NOT NULL
        )
    """)
    op.execute("CREATE INDEX task_events_by_task ON workspace.task_events (tenant_id, task_id, id)")
    op.execute("""
        CREATE TABLE workspace.tool_calls (
            tenant_id uuid NOT NULL, task_id uuid NOT NULL, tool_call_id text NOT NULL,
            tool_name text NOT NULL, result jsonb NOT NULL, created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, task_id, tool_call_id)
        )
    """)
    op.execute("""
        CREATE TABLE workspace.idempotency_keys (
            tenant_id uuid NOT NULL, user_id uuid NOT NULL, key text NOT NULL,
            response jsonb NOT NULL, created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, user_id, key)
        )
    """)
    for t in ("conversations", "tasks", "messages", "task_steps", "task_events", "tool_calls",
              "idempotency_keys"):
        tenant_rls(f"workspace.{t}")
    grant_schema("workspace")


def downgrade() -> None:
    op.execute("DROP SCHEMA workspace CASCADE")
