"""Analytics: dataset, snapshot, versiyali canonical satrlar, karantin, metrika sozlamalari,
query natijalari.

Satr versiyasi: snapshot S uchun `valid_from_seq <= S AND (valid_to_seq IS NULL OR valid_to_seq > S)`.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
from rls import grant_schema, tenant_rls  # type: ignore[import-not-found]

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

VERSIONED = """
    tenant_id uuid NOT NULL, dataset_id uuid NOT NULL, source_id text NOT NULL,
    source_revision text, row_hash char(64) NOT NULL,
    valid_from_seq integer NOT NULL, valid_to_seq integer,
"""
MONEY = "numeric(20,4)"


def upgrade() -> None:
    op.execute("CREATE SCHEMA analytics")
    op.execute("""
        CREATE TABLE analytics.datasets (
            tenant_id uuid NOT NULL, id uuid NOT NULL, data_source_id uuid NOT NULL,
            entity text NOT NULL, is_active boolean NOT NULL,
            latest_seq integer NOT NULL DEFAULT 0, latest_snapshot_id uuid,
            created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id), UNIQUE (tenant_id, data_source_id, entity)
        )
    """)
    # Har entity uchun bitta faol dataset: turli manbalar yig‘indisi ikki marta sanalmaydi.
    op.execute("""
        CREATE UNIQUE INDEX datasets_one_active_per_entity
        ON analytics.datasets (tenant_id, entity) WHERE is_active
    """)
    op.execute("""
        CREATE TABLE analytics.snapshots (
            tenant_id uuid NOT NULL, id uuid NOT NULL, dataset_id uuid NOT NULL, seq integer NOT NULL,
            batch_id uuid NOT NULL, sync_run_id uuid NOT NULL, as_of timestamptz NOT NULL,
            row_count integer NOT NULL, inserted_count integer NOT NULL, closed_count integer NOT NULL,
            quarantined_count integer NOT NULL, created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id), UNIQUE (tenant_id, dataset_id, seq),
            UNIQUE (tenant_id, dataset_id, batch_id),
            FOREIGN KEY (tenant_id, dataset_id) REFERENCES analytics.datasets (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE analytics.quarantine (
            tenant_id uuid NOT NULL, id uuid NOT NULL, dataset_id uuid NOT NULL,
            snapshot_id uuid NOT NULL, source_id text, reason text NOT NULL, record jsonb NOT NULL,
            created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id)
        )
    """)
    op.execute(f"""
        CREATE TABLE analytics.order_lines ({VERSIONED}
            occurred_at timestamptz NOT NULL, local_date date NOT NULL, document_number text NOT NULL,
            branch_code text NOT NULL, branch_name text NOT NULL,
            product_code text NOT NULL, product_name text NOT NULL,
            customer_code text NOT NULL, customer_name text,
            quantity {MONEY} NOT NULL, unit_price {MONEY} NOT NULL, gross_amount {MONEY} NOT NULL,
            discount_amount {MONEY} NOT NULL, discount_already_deducted boolean NOT NULL,
            vat_amount {MONEY} NOT NULL, amount_includes_vat boolean NOT NULL,
            currency char(3) NOT NULL, status text NOT NULL, cost_amount {MONEY},
            PRIMARY KEY (tenant_id, dataset_id, source_id, valid_from_seq)
        )
    """)
    op.execute(f"""
        CREATE TABLE analytics.returns ({VERSIONED}
            occurred_at timestamptz NOT NULL, local_date date NOT NULL, original_order_source_id text,
            branch_code text NOT NULL, product_code text NOT NULL, customer_code text NOT NULL,
            quantity {MONEY} NOT NULL, amount {MONEY} NOT NULL, vat_amount {MONEY} NOT NULL,
            amount_includes_vat boolean NOT NULL, currency char(3) NOT NULL, status text NOT NULL,
            cost_amount {MONEY},
            PRIMARY KEY (tenant_id, dataset_id, source_id, valid_from_seq)
        )
    """)
    op.execute(f"""
        CREATE TABLE analytics.receivables ({VERSIONED}
            customer_code text NOT NULL, customer_name text NOT NULL, document_number text NOT NULL,
            issued_on date NOT NULL, due_on date NOT NULL, amount {MONEY} NOT NULL,
            paid_amount {MONEY} NOT NULL, currency char(3) NOT NULL, branch_code text NOT NULL,
            PRIMARY KEY (tenant_id, dataset_id, source_id, valid_from_seq)
        )
    """)
    op.execute(f"""
        CREATE TABLE analytics.inventory_movements ({VERSIONED}
            occurred_at timestamptz NOT NULL, local_date date NOT NULL, warehouse_code text NOT NULL,
            branch_code text NOT NULL, product_code text NOT NULL, quantity_delta {MONEY} NOT NULL,
            movement_type text NOT NULL, unit_cost {MONEY}, currency char(3),
            PRIMARY KEY (tenant_id, dataset_id, source_id, valid_from_seq)
        )
    """)
    for t in ("order_lines", "returns", "inventory_movements"):
        op.execute(f"""
            CREATE INDEX {t}_open_by_date ON analytics.{t} (tenant_id, dataset_id, local_date)
            WHERE valid_to_seq IS NULL
        """)
    op.execute("""
        CREATE TABLE analytics.metric_settings (
            tenant_id uuid NOT NULL, version integer NOT NULL, settings jsonb NOT NULL,
            approved_by uuid NOT NULL, approved_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, version)
        )
    """)
    op.execute("""
        CREATE TABLE analytics.query_specs (
            tenant_id uuid NOT NULL, id uuid NOT NULL, kind text NOT NULL,
            spec jsonb NOT NULL, snapshot_ids uuid[] NOT NULL, result jsonb NOT NULL,
            created_by uuid NOT NULL, task_id uuid, created_at timestamptz NOT NULL,
            PRIMARY KEY (tenant_id, id)
        )
    """)
    for t in ("datasets", "snapshots", "quarantine", "order_lines", "returns", "receivables",
              "inventory_movements", "metric_settings", "query_specs"):
        tenant_rls(f"analytics.{t}")
    grant_schema("analytics")


def downgrade() -> None:
    op.execute("DROP SCHEMA analytics CASCADE")
