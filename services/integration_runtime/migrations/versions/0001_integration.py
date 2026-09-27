"""Integration Runtime: data source, mapping versiyalari, sync run, batch, lease navbati, messaging.

Revision ID: 0001
Revises:
"""

import os

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP = os.environ.get("INTEGRATION_APP_ROLE", "integration_app")
TENANT_TABLES = ["data_sources", "source_mappings", "sync_runs", "batches"]


def upgrade() -> None:
    op.execute("CREATE SCHEMA platform")
    op.execute("""
        CREATE FUNCTION platform.current_tenant_id() RETURNS uuid LANGUAGE sql STABLE AS
        $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$
    """)
    op.execute("CREATE SCHEMA integration")
    op.execute("""
        CREATE TABLE integration.data_sources (
            tenant_id uuid NOT NULL, id uuid NOT NULL, connector_id text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE integration.source_mappings (
            tenant_id uuid NOT NULL, data_source_id uuid NOT NULL, version integer NOT NULL,
            entity text NOT NULL, config jsonb NOT NULL, mapping jsonb NOT NULL,
            approved_by uuid NOT NULL, approved_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, data_source_id, version),
            FOREIGN KEY (tenant_id, data_source_id) REFERENCES integration.data_sources (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE integration.sync_runs (
            tenant_id uuid NOT NULL, id uuid NOT NULL, data_source_id uuid NOT NULL,
            connector_id text NOT NULL, mode text NOT NULL, mapping_version integer NOT NULL,
            object_ref jsonb, requested_by uuid NOT NULL,
            status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'partial', 'failed')),
            record_count integer NOT NULL DEFAULT 0, rejected_count integer NOT NULL DEFAULT 0,
            rejection_samples jsonb NOT NULL DEFAULT '[]', error_code text,
            correlation_id uuid NOT NULL, causation_id uuid NOT NULL, traceparent text,
            created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz,
            PRIMARY KEY (tenant_id, id), UNIQUE (id),
            FOREIGN KEY (tenant_id, data_source_id) REFERENCES integration.data_sources (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE integration.batches (
            tenant_id uuid NOT NULL, id uuid NOT NULL, sync_run_id uuid NOT NULL,
            data_source_id uuid NOT NULL, connector_id text NOT NULL, connector_version text NOT NULL,
            entity text NOT NULL, canonical_schema_version integer NOT NULL,
            record_count integer NOT NULL, object_ref jsonb NOT NULL,
            extracted_at timestamptz NOT NULL, is_full_snapshot boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, id), UNIQUE (sync_run_id, entity)
        )
    """)
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE integration.{t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE integration.{t} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON integration.{t}
            USING (tenant_id = platform.current_tenant_id())
            WITH CHECK (tenant_id = platform.current_tenant_id())
        """)
    # Lease navbati: faqat ID va lease maydonlari (tenant ma’lumoti yo‘q) — runner tenant’dan
    # oldin ishni tanlashi uchun RLS’siz; run tafsiloti keyin RLS ostida o‘qiladi.
    op.execute("""
        CREATE TABLE integration.run_queue (
            sync_run_id uuid PRIMARY KEY, tenant_id uuid NOT NULL,
            available_at timestamptz NOT NULL DEFAULT now(), attempts integer NOT NULL DEFAULT 0,
            lease_owner text, lease_expires_at timestamptz
        )
    """)
    op.execute("CREATE SCHEMA messaging")
    op.execute("""
        CREATE TABLE messaging.outbox (
            id bigserial PRIMARY KEY, event_id uuid NOT NULL UNIQUE, event_type text NOT NULL,
            routing_key text NOT NULL, tenant_id uuid NOT NULL, envelope jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(), attempts integer NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT now(), sent_at timestamptz,
            failed_at timestamptz, last_error text
        )
    """)
    op.execute("""
        CREATE INDEX outbox_pending_idx ON messaging.outbox (next_attempt_at, id)
        WHERE sent_at IS NULL AND failed_at IS NULL
    """)
    op.execute("""
        CREATE TABLE messaging.inbox (
            event_id uuid NOT NULL, consumer text NOT NULL,
            processed_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (event_id, consumer)
        )
    """)
    for schema in ("platform", "integration", "messaging"):
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {APP}")
    op.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA platform TO {APP}")
    for schema in ("integration", "messaging"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {APP}")
        op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA {schema} TO {APP}")


def downgrade() -> None:
    for schema in ("messaging", "integration", "platform"):
        op.execute(f"DROP SCHEMA {schema} CASCADE")
