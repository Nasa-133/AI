"""Hujjatlar (TZ 9): hujjat, versiya, bo‘lim, qidiruv parchalari (FTS + vektor), tozalash job’i.

Revision ID: 0009
Revises: 0008
"""

from alembic import op
from rls import grant_schema, tenant_rls  # type: ignore[import-not-found]

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA documents")
    op.execute("""
        CREATE TABLE documents.documents (
            tenant_id uuid NOT NULL, id uuid NOT NULL, title text NOT NULL,
            current_version_id uuid, visibility text NOT NULL DEFAULT 'tenant'
                CHECK (visibility IN ('private', 'tenant')),
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleting', 'deleted')),
            created_by uuid NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
            deleted_at timestamptz,
            PRIMARY KEY (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE documents.document_shares (
            tenant_id uuid NOT NULL, document_id uuid NOT NULL, user_id uuid NOT NULL,
            created_by uuid NOT NULL, created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, document_id, user_id),
            FOREIGN KEY (tenant_id, document_id) REFERENCES documents.documents (tenant_id, id)
                ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE documents.versions (
            tenant_id uuid NOT NULL, id uuid NOT NULL, document_id uuid NOT NULL,
            version_no integer NOT NULL, kind text NOT NULL CHECK (kind IN ('original', 'draft')),
            base_version_id uuid, filename text NOT NULL, content_type text NOT NULL,
            bucket text NOT NULL, object_key text NOT NULL, sha256 char(64) NOT NULL,
            size_bytes bigint NOT NULL,
            parse_status text NOT NULL CHECK (parse_status IN
                ('pending', 'parsing', 'ready', 'needs_ocr', 'failed')),
            parse_error text, quality jsonb NOT NULL DEFAULT '{}',
            embedding_status text NOT NULL DEFAULT 'none' CHECK (embedding_status IN
                ('none', 'pending', 'ready', 'failed')),
            comment text, created_by uuid NOT NULL, created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id), UNIQUE (tenant_id, document_id, version_no),
            FOREIGN KEY (tenant_id, document_id) REFERENCES documents.documents (tenant_id, id)
                ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE documents.sections (
            tenant_id uuid NOT NULL, version_id uuid NOT NULL, section_id text NOT NULL,
            ordinal integer NOT NULL, kind text NOT NULL, locator text NOT NULL, text text NOT NULL,
            PRIMARY KEY (tenant_id, version_id, section_id),
            FOREIGN KEY (tenant_id, version_id) REFERENCES documents.versions (tenant_id, id)
                ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE documents.chunks (
            tenant_id uuid NOT NULL, id uuid NOT NULL, document_id uuid NOT NULL,
            version_id uuid NOT NULL, ordinal integer NOT NULL, section_ids text[] NOT NULL,
            locator text NOT NULL, text text NOT NULL, search_text text NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', search_text)) STORED,
            embedding vector, embedding_model text,
            PRIMARY KEY (tenant_id, id),
            FOREIGN KEY (tenant_id, version_id) REFERENCES documents.versions (tenant_id, id)
                ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX chunks_tsv_idx ON documents.chunks USING gin (tsv)")
    op.execute("CREATE INDEX chunks_version_idx ON documents.chunks (tenant_id, version_id)")
    op.execute("""
        CREATE TABLE documents.cleanup_jobs (
            tenant_id uuid NOT NULL, id uuid NOT NULL, document_id uuid NOT NULL,
            status text NOT NULL CHECK (status IN ('pending', 'done', 'failed')),
            attempts integer NOT NULL DEFAULT 0, last_error text,
            created_at timestamptz NOT NULL, finished_at timestamptz,
            PRIMARY KEY (tenant_id, id)
        )
    """)
    for t in ("documents", "document_shares", "versions", "sections", "chunks", "cleanup_jobs"):
        tenant_rls(f"documents.{t}")
    grant_schema("documents")


def downgrade() -> None:
    op.execute("DROP SCHEMA documents CASCADE")
