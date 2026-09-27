"""Canonical record’larni o‘qish (contracts/canonical/*.v1.json bilan mos Pydantic modellar).

Kontraktga mos kelmagan satr — producer xatosi: butun batch doimiy xato bilan rad etiladi.
Mos kelishini `tests/contract/test_canonical_models.py` kontrakt fixture’lari bilan tekshiradi.
"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, ValidationError

from business.kernel.errors import BusinessError

from ..domain.ingestion import Entity

DecimalStr = Annotated[str, StringConstraints(pattern=r"^-?\d+(\.\d+)?$")]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Code = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Name = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Status = Literal["confirmed", "draft", "cancelled"]


class ContractViolation(BusinessError):
    code = "CANONICAL_CONTRACT_VIOLATION"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False, frozen=True)


class OrderLine(_Strict):
    source_id: Code
    source_revision: Annotated[str, StringConstraints(max_length=200)] | None
    document_number: Code
    occurred_at: AwareDatetime
    branch_code: Code
    branch_name: Name
    product_code: Code
    product_name: Name
    customer_code: Code
    customer_name: Name | None
    quantity: DecimalStr
    unit_price: DecimalStr
    gross_amount: DecimalStr
    discount_amount: DecimalStr
    discount_already_deducted: bool
    vat_amount: DecimalStr
    amount_includes_vat: bool
    currency: Currency
    status: Status
    cost_amount: DecimalStr | None


class Return(_Strict):
    source_id: Code
    source_revision: Annotated[str, StringConstraints(max_length=200)] | None
    original_order_source_id: Code | None
    occurred_at: AwareDatetime
    branch_code: Code
    product_code: Code
    customer_code: Code
    quantity: DecimalStr
    amount: DecimalStr
    vat_amount: DecimalStr
    amount_includes_vat: bool
    currency: Currency
    cost_amount: DecimalStr | None
    status: Status


class Receivable(_Strict):
    source_id: Code
    source_revision: Annotated[str, StringConstraints(max_length=200)] | None
    customer_code: Code
    customer_name: Name
    document_number: Code
    issued_on: date
    due_on: date
    amount: DecimalStr
    paid_amount: DecimalStr
    currency: Currency
    branch_code: Code


class Movement(_Strict):
    source_id: Code
    occurred_at: AwareDatetime
    warehouse_code: Code
    branch_code: Code
    product_code: Code
    quantity_delta: DecimalStr
    movement_type: Literal["receipt", "sale", "return", "transfer_in", "transfer_out", "adjustment"]
    unit_cost: DecimalStr | None
    currency: Currency | None


MODELS: dict[Entity, type[_Strict]] = {
    Entity.SALES_ORDER_LINE: OrderLine,
    Entity.SALES_RETURN: Return,
    Entity.FINANCE_RECEIVABLE: Receivable,
    Entity.INVENTORY_MOVEMENT: Movement,
}


def parse_line(entity: Entity, line: bytes, line_number: int) -> dict[str, Any]:
    """JSON satrini tekshiradi; qaytgan dict’da `_row_hash` o‘zgarishni aniqlash uchun."""
    try:
        raw = json.loads(line)
        model = MODELS[entity].model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ContractViolation(f"{entity} batch’ining {line_number}-satri kontraktga mos emas: "
                                f"{exc}") from exc
    record: dict[str, Any] = model.model_dump()
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    record["_row_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    return record


def to_decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def to_db_row(entity: Entity, r: dict[str, Any], tz_local_date: date | None) -> dict[str, Any]:
    """Domen tekshiruvidan o‘tgan satrni DB ustunlariga moslash (Decimal, lokal sana)."""
    common = {"source_id": r["source_id"], "source_revision": r.get("source_revision"),
              "row_hash": r["_row_hash"]}
    money = {k: to_decimal(v) for k, v in r.items()
             if k in {"quantity", "unit_price", "gross_amount", "discount_amount", "vat_amount",
                      "cost_amount", "amount", "paid_amount", "quantity_delta", "unit_cost"}}
    rest = {k: v for k, v in r.items()
            if k not in money and k not in common and not k.startswith("_")}
    row = {**common, **rest, **money}
    if entity is not Entity.FINANCE_RECEIVABLE:
        assert tz_local_date is not None
        row["local_date"] = tz_local_date
    return row


def local_date(occurred_at: datetime, timezone: str) -> date:
    from zoneinfo import ZoneInfo

    return occurred_at.astimezone(ZoneInfo(timezone)).date()


class S3CanonicalBatchReader:
    """CanonicalBatchReader porti: S3 obyekt → tekshirilgan record’lar."""

    def __init__(self, storage: Any) -> None:
        self._storage = storage

    async def read(self, object_ref: dict[str, Any], entity: Entity) -> list[dict[str, Any]]:
        from business.platform.storage import ObjectRef

        records = []
        number = 0
        async for line in self._storage.read_lines(ObjectRef.from_json(object_ref)):
            number += 1
            records.append(parse_line(entity, line, number))
        return records
