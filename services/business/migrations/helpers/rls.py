"""Migratsiyalar uchun yordamchi: tenant jadvaliga FORCE RLS va app roli huquqlari.

Diqqat: bu fayl migratsiya tarixining bir qismi — o‘zgartirilsa eski migratsiyalar ham
o‘zgaradi. Yangi xatti-harakat kerak bo‘lsa yangi funksiya qo‘shing.
"""

import os

from alembic import op

APP_ROLE = os.environ.get("BUSINESS_APP_ROLE", "business_app")


def tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation ON {table}
        USING (tenant_id = platform.current_tenant_id())
        WITH CHECK (tenant_id = platform.current_tenant_id())
    """)


def grant_schema(schema: str) -> None:
    op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA {schema} TO {APP_ROLE}")
