"""Entity → jadval va ustunlar (migratsiya 0005 bilan mos)."""

from ..domain.ingestion import Entity

TABLES: dict[Entity, str] = {
    Entity.SALES_ORDER_LINE: "analytics.order_lines",
    Entity.SALES_RETURN: "analytics.returns",
    Entity.FINANCE_RECEIVABLE: "analytics.receivables",
    Entity.INVENTORY_MOVEMENT: "analytics.inventory_movements",
}

_COMMON = ["source_id", "source_revision", "row_hash"]

COLUMNS: dict[Entity, list[str]] = {
    Entity.SALES_ORDER_LINE: [*_COMMON, "occurred_at", "local_date", "document_number",
                              "branch_code", "branch_name", "product_code", "product_name",
                              "customer_code", "customer_name", "quantity", "unit_price",
                              "gross_amount", "discount_amount", "discount_already_deducted",
                              "vat_amount", "amount_includes_vat", "currency", "status",
                              "cost_amount"],
    Entity.SALES_RETURN: [*_COMMON, "occurred_at", "local_date", "original_order_source_id",
                          "branch_code", "product_code", "customer_code", "quantity", "amount",
                          "vat_amount", "amount_includes_vat", "currency", "status",
                          "cost_amount"],
    Entity.FINANCE_RECEIVABLE: [*_COMMON, "customer_code", "customer_name", "document_number",
                                "issued_on", "due_on", "amount", "paid_amount", "currency",
                                "branch_code"],
    Entity.INVENTORY_MOVEMENT: ["source_id", "source_revision", "row_hash", "occurred_at",
                                "local_date", "warehouse_code", "branch_code", "product_code",
                                "quantity_delta", "movement_type", "unit_cost", "currency"],
}

VISIBLE = ("{a}dataset_id = :{p}ds AND {a}valid_from_seq <= :{p}seq"
           " AND ({a}valid_to_seq IS NULL OR {a}valid_to_seq > :{p}seq)")


def visible(alias: str = "", prefix: str = "") -> str:
    """Snapshot `seq` holatidagi satrlar (satr versiyalash, migratsiya 0005)."""
    return VISIBLE.format(a=f"{alias}." if alias else "", p=prefix)
