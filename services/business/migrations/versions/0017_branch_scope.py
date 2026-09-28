"""S02: a’zoning filial doirasi (NULL — barcha filiallar).

Revision ID: 0017
Revises: 0016
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE identity.memberships ADD COLUMN branch_scope text[]")
    op.execute("""
        ALTER TABLE identity.memberships ADD CONSTRAINT memberships_branch_scope_nonempty
        CHECK (branch_scope IS NULL OR cardinality(branch_scope) BETWEEN 1 AND 200)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE identity.memberships DROP COLUMN branch_scope")
