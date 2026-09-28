"""Bir obyekt uchun bir nechta manba (yig‘iladi) va takroriy baza himoyasi.

Oldin: har obyekt uchun bitta faol dataset (qolganlari e’tiborsiz). Endi: barcha faol datasetlar
qo‘shib hisoblanadi; boshqa faol manba bilan asosan bir xil yozuvlarni beradigan dataset
“takroriy” deb belgilanadi (duplicate_of) va hisobga olinmaydi — bir baza ikki marta sanalmaydi.

Revision ID: 0018
Revises: 0017
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX analytics.datasets_one_active_per_entity")
    op.execute("ALTER TABLE analytics.datasets ADD COLUMN duplicate_of uuid")
    op.execute("ALTER TABLE analytics.datasets ADD COLUMN overlap numeric(5, 4)")
    op.execute("CREATE INDEX datasets_active_by_entity ON analytics.datasets"
                " (tenant_id, entity) WHERE is_active")
    for table in ("order_lines", "returns", "receivables", "inventory_movements"):
        op.execute(f"CREATE INDEX IF NOT EXISTS {table}_open_source_id ON analytics.{table}"
                   " (tenant_id, source_id) WHERE valid_to_seq IS NULL")


def downgrade() -> None:
    for table in ("order_lines", "returns", "receivables", "inventory_movements"):
        op.execute(f"DROP INDEX IF EXISTS analytics.{table}_open_source_id")
    op.execute("DROP INDEX analytics.datasets_active_by_entity")
    # Qaytishda eski invariant: har obyekt uchun faqat eng eski faol dataset qoladi.
    op.execute("""
        UPDATE analytics.datasets d SET is_active = false
        WHERE is_active AND EXISTS (SELECT 1 FROM analytics.datasets o
            WHERE o.tenant_id = d.tenant_id AND o.entity = d.entity AND o.is_active
            AND (o.created_at, o.id) < (d.created_at, d.id))
    """)
    op.execute("ALTER TABLE analytics.datasets DROP COLUMN overlap")
    op.execute("ALTER TABLE analytics.datasets DROP COLUMN duplicate_of")
    op.execute("CREATE UNIQUE INDEX datasets_one_active_per_entity"
                " ON analytics.datasets (tenant_id, entity) WHERE is_active")
