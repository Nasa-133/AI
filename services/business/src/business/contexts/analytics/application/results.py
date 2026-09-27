"""Komponent qatorlaridan tool natijasi jadvalini yig‘ish (contracts/tools/*.result.v1.json)."""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from ..domain.metrics import Component, Dimension, MetricDefinition, Unit, compute
from ..ports.store import ComponentRow

MONEY_QUANT = Decimal("0.01")
NAMED = (Dimension.BRANCH, Dimension.PRODUCT, Dimension.CUSTOMER)


def fmt(value: Decimal | None, unit: Unit) -> str | None:
    if value is None:
        return None
    if unit is Unit.COUNT:
        return str(int(value))
    return str(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def dimension_columns(dims: Sequence[Dimension], with_currency: bool) -> list[dict[str, Any]]:
    cols = []
    for d in dims:
        if d is Dimension.CURRENCY:
            continue
        cols.append({"name": d.value, "kind": "dimension", "metric_id": None, "unit": None})
        if d in NAMED:
            cols.append({"name": f"{d.value}_name", "kind": "dimension", "metric_id": None,
                         "unit": None})
    if with_currency:
        cols.append({"name": "currency", "kind": "dimension", "metric_id": None, "unit": None})
    return cols


def dimension_cells(key: tuple[str, ...], dims: Sequence[Dimension], with_currency: bool,
                    names: dict[Dimension, dict[str, str]]) -> list[str | None]:
    cells: list[str | None] = []
    plain = [d for d in dims if d is not Dimension.CURRENCY]
    for i, d in enumerate(plain):
        cells.append(key[i])
        if d in NAMED:
            cells.append(names.get(d, {}).get(key[i]))
    if with_currency:
        cells.append(key[-1])
    return cells


def metric_cells(values: dict[Component, Decimal],
                 definitions: Sequence[MetricDefinition]) -> tuple[list[str | None], list[str]]:
    cells, notes = [], []
    for d in definitions:
        v = compute(d.id, values)
        cells.append(fmt(v.value, d.unit))
        if v.note:
            notes.append(v.note)
    return cells, notes


def aggregate_totals(rows: Sequence[ComponentRow]) -> dict[str, dict[Component, Decimal]]:
    """Valyuta bo‘yicha jami (valyutalar qo‘shilmaydi)."""
    totals: dict[str, dict[Component, Decimal]] = {}
    for r in rows:
        acc = totals.setdefault(r.key[-1], {})
        for c, v in r.values.items():
            acc[c] = acc.get(c, Decimal("0")) + v
    return totals
