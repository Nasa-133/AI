"""Audit jurnali (TZ 17–18): kim, qachon, nima qildi. Faqat qo‘shiladi (app roli UPDATE/DELETE
qila olmaydi); saqlash muddati tugaganini faqat `governance.purge_audit` o‘chiradi.

Revision ID: 0014
Revises: 0013
"""

from alembic import op
from rls import APP_ROLE, tenant_rls  # type: ignore[import-not-found]

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE governance.audit_events (
            tenant_id uuid NOT NULL, id bigserial, actor_id uuid,
            actor_kind text NOT NULL CHECK (actor_kind IN ('user', 'agent', 'system')),
            action text NOT NULL, target_type text, target_id text,
            details jsonb NOT NULL DEFAULT '{}', ip text, created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id)
        )
    """)
    op.execute("CREATE INDEX audit_by_time ON governance.audit_events (tenant_id, created_at DESC)")
    tenant_rls("governance.audit_events")
    op.execute(f"GRANT SELECT, INSERT ON governance.audit_events TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON SEQUENCE governance.audit_events_id_seq TO {APP_ROLE}")
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON governance.audit_events FROM {APP_ROLE}")
    # Joriy tenant (RLS) doirasida muddati o‘tganlarni o‘chiradi; minimal saqlash — 30 kun.
    op.execute("""
        CREATE FUNCTION governance.purge_audit(keep_days integer) RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
        DECLARE n bigint;
        BEGIN
            DELETE FROM governance.audit_events
            WHERE created_at < now() - make_interval(days => greatest(keep_days, 30));
            GET DIAGNOSTICS n = ROW_COUNT;
            RETURN n;
        END $$
    """)
    op.execute("REVOKE ALL ON FUNCTION governance.purge_audit(integer) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION governance.purge_audit(integer) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION governance.purge_audit(integer)")
    op.execute("DROP TABLE governance.audit_events")
