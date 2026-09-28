"""App roli pgvector turini ishlata olsin: `vector` extension’i public sxemada.

Init skripti public’dan PUBLIC huquqlarini oladi; app roliga faqat USAGE (CREATE emas)
beriladi — aks holda `CAST(... AS vector)` “type does not exist” bilan yiqiladi.

Revision ID: 0010
Revises: 0009
"""

from alembic import op
from rls import APP_ROLE  # type: ignore[import-not-found]

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
