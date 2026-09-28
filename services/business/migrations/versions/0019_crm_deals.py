"""CRM: bitimlar (savdo voronkasi) — versiyali satrlar, boshqa analitik jadvallar kabi.

created_date / closed_date — tenant vaqt mintaqasidagi sana (oylar kesimi va davr filtri uchun).

Revision ID: 0019
Revises: 0018
"""

from alembic import op
from rls import grant_schema, tenant_rls  # type: ignore[import-not-found]

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

VERSIONED = """
    tenant_id uuid NOT NULL, dataset_id uuid NOT NULL, source_id text NOT NULL,
    source_revision text, row_hash char(64) NOT NULL,
    valid_from_seq integer NOT NULL, valid_to_seq integer,
"""
MONEY = "numeric(20,4)"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE analytics.deals ({VERSIONED}
            deal_number text NOT NULL, customer_code text NOT NULL, customer_name text,
            branch_code text NOT NULL, stage text NOT NULL, status text NOT NULL,
            amount {MONEY} NOT NULL, currency char(3) NOT NULL,
            created_at timestamptz NOT NULL, created_date date NOT NULL,
            closed_at timestamptz, closed_date date, channel text,
            PRIMARY KEY (tenant_id, dataset_id, source_id, valid_from_seq)
        )
    """)
    op.execute("CREATE INDEX deals_open_by_created ON analytics.deals"
               " (tenant_id, dataset_id, created_date) WHERE valid_to_seq IS NULL")
    op.execute("CREATE INDEX deals_open_source_id ON analytics.deals"
               " (tenant_id, source_id) WHERE valid_to_seq IS NULL")
    tenant_rls("analytics.deals")
    grant_schema("analytics")


def downgrade() -> None:
    op.execute("DROP TABLE analytics.deals")
