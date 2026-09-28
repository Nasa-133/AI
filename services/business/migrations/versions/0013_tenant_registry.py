"""Fon ishlari uchun tenant ro‘yxati (faqat ID): worker har tenant uchun alohida RLS
kontekstida ishlaydi. `identity.tenants` FORCE RLS ostida qoladi — nom va sozlamalar ochilmaydi.

Revision ID: 0013
Revises: 0012
"""

from alembic import op
from rls import APP_ROLE  # type: ignore[import-not-found]

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE platform.tenant_registry (id uuid PRIMARY KEY,"
               " created_at timestamptz NOT NULL DEFAULT now())")
    op.execute(f"GRANT SELECT ON platform.tenant_registry TO {APP_ROLE}")
    # Mavjud tenantlar: owner ham FORCE RLS’ga bo‘ysunadi — backfill paytida vaqtincha o‘chiriladi.
    op.execute("ALTER TABLE identity.tenants NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identity.tenants DISABLE ROW LEVEL SECURITY")
    op.execute("INSERT INTO platform.tenant_registry (id, created_at)"
               " SELECT id, created_at FROM identity.tenants ON CONFLICT DO NOTHING")
    op.execute("ALTER TABLE identity.tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identity.tenants FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE FUNCTION platform.register_tenant() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
        BEGIN
            INSERT INTO platform.tenant_registry (id, created_at) VALUES (NEW.id, NEW.created_at)
            ON CONFLICT DO NOTHING;
            RETURN NEW;
        END $$
    """)
    op.execute("REVOKE ALL ON FUNCTION platform.register_tenant() FROM PUBLIC")
    op.execute("CREATE TRIGGER tenants_register AFTER INSERT ON identity.tenants"
               " FOR EACH ROW EXECUTE FUNCTION platform.register_tenant()")


def downgrade() -> None:
    op.execute("DROP TRIGGER tenants_register ON identity.tenants")
    op.execute("DROP FUNCTION platform.register_tenant()")
    op.execute("DROP TABLE platform.tenant_registry")
