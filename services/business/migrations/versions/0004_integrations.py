"""Integrations (Core proyeksiyasi): yuklangan fayllar, data source, mapping, sync run.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
from rls import grant_schema, tenant_rls  # type: ignore[import-not-found]

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLES = ["uploads", "data_sources", "source_mappings", "sync_runs"]


def upgrade() -> None:
    op.execute("CREATE SCHEMA integrations")
    op.execute("""
        CREATE TABLE integrations.uploads (
            tenant_id uuid NOT NULL, id uuid NOT NULL,
            purpose text NOT NULL CHECK (purpose IN ('document', 'dataset_import')),
            filename text NOT NULL, content_type text NOT NULL, size_bytes bigint NOT NULL,
            sha256 char(64) NOT NULL, bucket text NOT NULL, object_key text NOT NULL,
            created_by uuid NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE integrations.data_sources (
            tenant_id uuid NOT NULL, id uuid NOT NULL, name text NOT NULL,
            connector_id text NOT NULL, upload_id uuid,
            status text NOT NULL, entity text, discovery jsonb,
            mapping_version integer, last_sync_run_id uuid, error_message text,
            created_by uuid NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id),
            FOREIGN KEY (tenant_id, upload_id) REFERENCES integrations.uploads (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE integrations.source_mappings (
            tenant_id uuid NOT NULL, data_source_id uuid NOT NULL, version integer NOT NULL,
            entity text NOT NULL, config jsonb NOT NULL, mapping jsonb NOT NULL,
            status text NOT NULL CHECK (status IN ('pending', 'accepted', 'rejected')),
            error_message text, approved_by uuid NOT NULL, approved_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, data_source_id, version),
            FOREIGN KEY (tenant_id, data_source_id) REFERENCES integrations.data_sources (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE integrations.sync_runs (
            tenant_id uuid NOT NULL, id uuid NOT NULL, data_source_id uuid NOT NULL,
            mapping_version integer NOT NULL,
            status text NOT NULL CHECK (status IN ('requested', 'succeeded', 'partial', 'failed')),
            requested_by uuid NOT NULL, requested_at timestamptz NOT NULL,
            finished_at timestamptz, result jsonb,
            PRIMARY KEY (tenant_id, id),
            FOREIGN KEY (tenant_id, data_source_id) REFERENCES integrations.data_sources (tenant_id, id)
        )
    """)
    for t in TABLES:
        tenant_rls(f"integrations.{t}")
    grant_schema("integrations")


def downgrade() -> None:
    op.execute("DROP SCHEMA integrations CASCADE")
