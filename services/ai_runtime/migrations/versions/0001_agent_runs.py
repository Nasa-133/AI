"""AI Runtime: agent_runs (FORCE RLS), run_queue (lease), messaging outbox/inbox.

Run’larni tenantlar bo‘ylab olish uchun `agent.run_queue` ishlatiladi: unda faqat
identifikatorlar va lease maydonlari bor (topshiriq matni, token, checkpoint yo‘q), shuning
uchun RLS’siz. Runner navbatdan run_id + tenant_id oladi, so‘ng tenant kontekstini bog‘lab
`agent_runs` satrini RLS ostida o‘qiydi. SECURITY DEFINER funksiya kerak emas.

Revision ID: 0001
Revises:
"""

import os

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("AI_APP_ROLE", "ai_app")


def upgrade() -> None:
    op.execute("CREATE SCHEMA platform")
    op.execute("""
        CREATE FUNCTION platform.current_tenant_id() RETURNS uuid
        LANGUAGE sql STABLE AS
        $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$
    """)

    op.execute("CREATE SCHEMA agent")
    op.execute("""
        CREATE TABLE agent.agent_runs (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL,
            task_id uuid NOT NULL,
            task_step_id uuid NOT NULL UNIQUE,
            role_key text NOT NULL,
            status text NOT NULL CHECK (status IN
                ('queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled')),
            instruction text NOT NULL,
            locale text NOT NULL,
            capability_token text NOT NULL,
            deadline timestamptz NOT NULL,
            correlation_id uuid NOT NULL,
            causation_id uuid NOT NULL,
            max_tool_calls integer NOT NULL,
            tool_calls_used integer NOT NULL DEFAULT 0,
            cancel_requested boolean NOT NULL DEFAULT false,
            sequence integer NOT NULL DEFAULT 0,
            checkpoint jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX agent_runs_tenant_idx ON agent.agent_runs (tenant_id)")
    op.execute("ALTER TABLE agent.agent_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent.agent_runs FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY agent_runs_tenant ON agent.agent_runs
        USING (tenant_id = platform.current_tenant_id())
        WITH CHECK (tenant_id = platform.current_tenant_id())
    """)

    op.execute("""
        CREATE TABLE agent.run_queue (
            run_id uuid PRIMARY KEY REFERENCES agent.agent_runs(id) ON DELETE CASCADE,
            tenant_id uuid NOT NULL,
            enqueued_at timestamptz NOT NULL DEFAULT now(),
            lease_owner text,
            lease_expires_at timestamptz
        )
    """)
    op.execute("CREATE INDEX run_queue_ready_idx ON agent.run_queue (lease_expires_at, enqueued_at)")

    op.execute("CREATE SCHEMA messaging")
    op.execute("""
        CREATE TABLE messaging.outbox (
            id bigserial PRIMARY KEY,
            event_id uuid NOT NULL UNIQUE,
            event_type text NOT NULL,
            routing_key text NOT NULL,
            tenant_id uuid NOT NULL,
            envelope jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            attempts integer NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT now(),
            sent_at timestamptz,
            failed_at timestamptz,
            last_error text
        )
    """)
    op.execute("""
        CREATE INDEX outbox_pending_idx ON messaging.outbox (next_attempt_at, id)
        WHERE sent_at IS NULL AND failed_at IS NULL
    """)
    op.execute("""
        CREATE TABLE messaging.inbox (
            event_id uuid NOT NULL,
            consumer text NOT NULL,
            processed_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (event_id, consumer)
        )
    """)

    op.execute(f"GRANT USAGE ON SCHEMA platform, agent, messaging TO {APP_ROLE}")
    op.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA platform TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA agent TO {APP_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA messaging TO {APP_ROLE}"
    )
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA messaging TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP SCHEMA messaging CASCADE")
    op.execute("DROP SCHEMA agent CASCADE")
    op.execute("DROP SCHEMA platform CASCADE")
