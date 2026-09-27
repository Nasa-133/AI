"""Canonical record maydonlari (contracts/canonical/*.v1.json bilan mos).

Integration faqat canonical record chiqaradi; Core faqat canonical record o‘qiydi (TZ 13.10).
Mos kelishi kontrakt testlarida jsonschema bilan tekshiriladi.
"""

from dataclasses import dataclass
from enum import StrEnum

CANONICAL_SCHEMA_VERSION = 1

STATUS_VALUES = ("confirmed", "draft", "cancelled")
MOVEMENT_TYPES = ("receipt", "sale", "return", "transfer_in", "transfer_out", "adjustment")


class FieldKind(StrEnum):
    TEXT = "text"
    DECIMAL = "decimal"
    DATETIME = "datetime"
    DATE = "date"
    BOOL = "bool"
    ENUM = "enum"
    CURRENCY = "currency"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    kind: FieldKind
    nullable: bool = False
    max_length: int = 200
    enum_values: tuple[str, ...] = ()


def _t(name: str, *, nullable: bool = False, max_length: int = 200) -> FieldSpec:
    return FieldSpec(name, FieldKind.TEXT, nullable=nullable, max_length=max_length)


def _d(name: str, *, nullable: bool = False) -> FieldSpec:
    return FieldSpec(name, FieldKind.DECIMAL, nullable=nullable)


ENTITY_FIELDS: dict[str, tuple[FieldSpec, ...]] = {
    "sales.order_line": (
        _t("source_id"),
        _t("source_revision", nullable=True),
        _t("document_number"),
        FieldSpec("occurred_at", FieldKind.DATETIME),
        _t("branch_code"),
        _t("branch_name", max_length=500),
        _t("product_code"),
        _t("product_name", max_length=500),
        _t("customer_code"),
        _t("customer_name", nullable=True, max_length=500),
        _d("quantity"),
        _d("unit_price"),
        _d("gross_amount"),
        _d("discount_amount"),
        FieldSpec("discount_already_deducted", FieldKind.BOOL),
        _d("vat_amount"),
        FieldSpec("amount_includes_vat", FieldKind.BOOL),
        FieldSpec("currency", FieldKind.CURRENCY),
        FieldSpec("status", FieldKind.ENUM, enum_values=STATUS_VALUES),
        _d("cost_amount", nullable=True),
    ),
    "sales.return": (
        _t("source_id"),
        _t("source_revision", nullable=True),
        _t("original_order_source_id", nullable=True),
        FieldSpec("occurred_at", FieldKind.DATETIME),
        _t("branch_code"),
        _t("product_code"),
        _t("customer_code"),
        _d("quantity"),
        _d("amount"),
        _d("vat_amount"),
        FieldSpec("amount_includes_vat", FieldKind.BOOL),
        FieldSpec("currency", FieldKind.CURRENCY),
        _d("cost_amount", nullable=True),
        FieldSpec("status", FieldKind.ENUM, enum_values=STATUS_VALUES),
    ),
    "inventory.movement": (
        _t("source_id"),
        FieldSpec("occurred_at", FieldKind.DATETIME),
        _t("warehouse_code"),
        _t("branch_code"),
        _t("product_code"),
        _d("quantity_delta"),
        FieldSpec("movement_type", FieldKind.ENUM, enum_values=MOVEMENT_TYPES),
        _d("unit_cost", nullable=True),
        FieldSpec("currency", FieldKind.CURRENCY, nullable=True),
    ),
    "finance.receivable": (
        _t("source_id"),
        _t("source_revision", nullable=True),
        _t("customer_code"),
        _t("customer_name", max_length=500),
        _t("document_number"),
        FieldSpec("issued_on", FieldKind.DATE),
        FieldSpec("due_on", FieldKind.DATE),
        _d("amount"),
        _d("paid_amount"),
        FieldSpec("currency", FieldKind.CURRENCY),
        _t("branch_code"),
    ),
}

ENTITIES = tuple(ENTITY_FIELDS)
