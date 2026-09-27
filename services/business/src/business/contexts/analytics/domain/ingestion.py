"""Canonical batch’ni qabul qilish qoidalari: semantik karantin (TZ 16, docs/design/stage1.md §5).

Integration normallashtira olmagan satrlarni o‘zi rad etadi; bu yerda — tuzilmasi to‘g‘ri,
lekin ma’nosi shubhali satrlar. Karantin satri saqlanadi va sababi ko‘rsatiladi.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

ZERO = Decimal("0")


class Entity(StrEnum):
    SALES_ORDER_LINE = "sales.order_line"
    SALES_RETURN = "sales.return"
    INVENTORY_MOVEMENT = "inventory.movement"
    FINANCE_RECEIVABLE = "finance.receivable"


@dataclass(frozen=True, slots=True)
class Quarantined:
    record: dict[str, Any]
    reason: str


@dataclass(frozen=True, slots=True)
class Screened:
    accepted: list[dict[str, Any]]
    quarantined: list[Quarantined]


def _record_problem(entity: Entity, r: dict[str, Any]) -> str | None:
    match entity:
        case Entity.SALES_ORDER_LINE:
            if Decimal(r["quantity"]) <= ZERO:
                return "Savdo miqdori musbat emas"
            if Decimal(r["gross_amount"]) < ZERO or Decimal(r["discount_amount"]) < ZERO:
                return "Savdo summasi yoki chegirma manfiy"
        case Entity.SALES_RETURN:
            if Decimal(r["quantity"]) <= ZERO or Decimal(r["amount"]) < ZERO:
                return "Qaytarish miqdori yoki summasi noto‘g‘ri"
        case Entity.FINANCE_RECEIVABLE:
            if Decimal(r["amount"]) < ZERO or Decimal(r["paid_amount"]) < ZERO:
                return "Debitorlik summasi manfiy"
            if r["due_on"] < r["issued_on"]:
                return "To‘lov muddati hujjat sanasidan oldin"
        case Entity.INVENTORY_MOVEMENT:
            pass
    return None


def screen(entity: Entity, records: Iterable[dict[str, Any]]) -> Screened:
    """Batch ichida takrorlangan `source_id` — barcha nusxalari karantinga (qaysi biri
    to‘g‘riligini taxmin qilmaymiz)."""
    rows = list(records)
    counts = Counter(r["source_id"] for r in rows)
    accepted: list[dict[str, Any]] = []
    quarantined: list[Quarantined] = []
    for r in rows:
        if counts[r["source_id"]] > 1:
            quarantined.append(Quarantined(r, f"source_id batch ichida {counts[r['source_id']]} "
                                              "marta takrorlangan"))
        elif (problem := _record_problem(entity, r)) is not None:
            quarantined.append(Quarantined(r, problem))
        else:
            accepted.append(r)
    return Screened(accepted, quarantined)
