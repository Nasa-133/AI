"""Business outbox/inbox (TZ 13.8). Shakl abo_messaging.store bilan mos.

Messaging jadvallari infratuzilma: RLS yo‘q (relay barcha tenantlar xabarini yuboradi),
lekin HTTP orqali hech qachon o‘qilmaydi.

Revision ID: 0003
Revises: 0002
"""

import os

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("BUSINESS_APP_ROLE", "business_app")


def upgrade() -> None:
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
    op.execute(f"GRANT USAGE ON SCHEMA messaging TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA messaging TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA messaging TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP SCHEMA messaging CASCADE")
