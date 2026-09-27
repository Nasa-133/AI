"""Yig‘indi (komponent) so‘rovlari. SQL faqat oq ro‘yxatdagi bo‘laklardan yig‘iladi; qiymatlar
har doim bind parametr. Metrika ma’nosi domain/metrics.py’da."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.ingestion import Entity
from ..domain.metrics import Component as C
from ..domain.metrics import Dimension as D
from ..domain.query import Filters, Period, QuerySpec
from ..ports.store import ComponentRow, Coverage, SnapshotRef
from .sql_tables import visible

_DIM_SQL = {
    D.MONTH: "to_char(local_date, 'YYYY-MM')",
    D.WEEK: "to_char(local_date, 'IYYY-\"W\"IW')",
    D.DAY: "to_char(local_date, 'YYYY-MM-DD')",
    D.BRANCH: "branch_code",
    D.PRODUCT: "product_code",
    D.CUSTOMER: "customer_code",
}
_NAME_SQL = {
    D.BRANCH: ("branch_code", "branch_name", "analytics.order_lines"),
    D.PRODUCT: ("product_code", "product_name", "analytics.order_lines"),
    D.CUSTOMER: ("customer_code", "customer_name", "analytics.order_lines"),
}
_ORDER_SUMS = {
    C.ORDER_NET: "sum(gross_amount - CASE WHEN amount_includes_vat THEN vat_amount ELSE 0 END"
                 " - CASE WHEN discount_already_deducted THEN 0 ELSE discount_amount END)",
    C.DISCOUNTS: "sum(discount_amount)",
    C.ORDER_COST: "coalesce(sum(cost_amount), 0)",
    C.COST_MISSING_ROWS: "count(*) FILTER (WHERE cost_amount IS NULL)",
    C.ORDER_COUNT: "count(DISTINCT document_number)",
    C.QUANTITY: "sum(quantity)",
}
_RETURN_SUMS = {
    C.RETURNS_NET: "sum(amount - CASE WHEN amount_includes_vat THEN vat_amount ELSE 0 END)",
    C.RETURN_COST: "coalesce(sum(cost_amount), 0)",
}


def _group_exprs(dims: tuple[D, ...]) -> list[str]:
    # Valyuta har doim guruhlanadi: turli valyutalar hech qachon qo‘shilmaydi.
    return [*(_DIM_SQL[d] for d in dims if d is not D.CURRENCY), "currency"]


def _filters(spec: QuerySpec, f: Filters, params: dict[str, Any], *,
             customers: bool = True, products: bool = True) -> str:
    sql = ""
    if spec.currency:
        sql += " AND currency = :currency"
        params["currency"] = spec.currency
    if f.branch_codes:
        sql += " AND branch_code = ANY(:branches)"
        params["branches"] = list(f.branch_codes)
    if products and f.product_codes:
        sql += " AND product_code = ANY(:products)"
        params["products"] = list(f.product_codes)
    if customers and f.customer_codes:
        sql += " AND customer_code = ANY(:customers)"
        params["customers"] = list(f.customer_codes)
    return sql


class SqlAggregates:
    def __init__(self, conn: AsyncConnection) -> None:
        self._c = conn

    async def _sums(self, table: str, snapshot: SnapshotRef, sums: dict[C, str],
                    spec: QuerySpec, period: Period, dims: tuple[D, ...],
                    where_extra: str = "") -> list[tuple[tuple[str, ...], dict[C, Decimal]]]:
        groups = _group_exprs(dims)
        params: dict[str, Any] = {"ds": snapshot.dataset_id, "seq": snapshot.seq,
                                  "start": period.start, "end": period.end}
        where = (f"{visible()} AND status = 'confirmed' AND local_date BETWEEN :start AND :end"
                 + where_extra + _filters(spec, spec.filters, params))
        select = ", ".join([*(f"{g} AS g{i}" for i, g in enumerate(groups)),
                            *(f"{expr} AS {c.value}" for c, expr in sums.items())])
        group_by = ", ".join(str(i + 1) for i in range(len(groups)))
        rows = (await self._c.execute(text(
            f"SELECT {select} FROM {table} WHERE {where} GROUP BY {group_by}"), params)).all()
        out = []
        for r in rows:
            m = r._mapping
            key = tuple(str(m[f"g{i}"]) for i in range(len(groups)))
            out.append((key, {c: Decimal(m[c.value] or 0) for c in sums}))
        return out

    async def sales_components(self, spec: QuerySpec, period: Period,
                               snapshots: dict[Entity, SnapshotRef],
                               dimensions: tuple[D, ...]) -> list[ComponentRow]:
        merged: dict[tuple[str, ...], dict[C, Decimal]] = defaultdict(dict)
        parts = [(Entity.SALES_ORDER_LINE, "analytics.order_lines", _ORDER_SUMS),
                 (Entity.SALES_RETURN, "analytics.returns", _RETURN_SUMS)]
        for entity, table, sums in parts:
            snap = snapshots.get(entity)
            if snap is None:
                continue
            for key, values in await self._sums(table, snap, sums, spec, period, dimensions):
                merged[key].update(values)
        return [ComponentRow(k, v) for k, v in sorted(merged.items())]

    async def receivable_components(self, spec: QuerySpec, as_of: date, snapshot: SnapshotRef,
                                    dimensions: tuple[D, ...]) -> list[ComponentRow]:
        groups = [*(_DIM_SQL[d] for d in dimensions if d is not D.CURRENCY), "currency"]
        params: dict[str, Any] = {"ds": snapshot.dataset_id, "seq": snapshot.seq, "as_of": as_of}
        where = (f"{visible()} AND issued_on <= :as_of"
                 + _filters(spec, spec.filters, params, products=False))
        open_amount = "GREATEST(amount - paid_amount, 0)"
        select = ", ".join([*(f"{g} AS g{i}" for i, g in enumerate(groups)),
                            f"sum({open_amount}) AS open",
                            f"coalesce(sum({open_amount}) FILTER (WHERE due_on < :as_of), 0)"
                            " AS overdue"])
        group_by = ", ".join(str(i + 1) for i in range(len(groups)))
        rows = (await self._c.execute(text(
            f"SELECT {select} FROM analytics.receivables WHERE {where} GROUP BY {group_by}"),
            params)).all()
        return [ComponentRow(tuple(str(r._mapping[f"g{i}"]) for i in range(len(groups))),
                             {C.RECEIVABLE_OPEN: Decimal(r.open or 0),
                              C.RECEIVABLE_OVERDUE: Decimal(r.overdue or 0)})
                for r in rows]

    async def dimension_names(self, dimension: D, codes: list[str],
                              snapshots: dict[Entity, SnapshotRef]) -> dict[str, str]:
        snap = snapshots.get(Entity.SALES_ORDER_LINE)
        if dimension not in _NAME_SQL or snap is None or not codes:
            return {}
        code_col, name_col, table = _NAME_SQL[dimension]
        rows = (await self._c.execute(text(
            f"SELECT {code_col} AS code, max({name_col}) AS name FROM {table}"
            f" WHERE {visible()} AND {code_col} = ANY(:codes) GROUP BY 1"),
            {"ds": snap.dataset_id, "seq": snap.seq, "codes": codes})).all()
        return {r.code: r.name for r in rows if r.name}

    async def coverage(self, snapshots: dict[Entity, SnapshotRef]) -> Coverage:
        snap = snapshots.get(Entity.SALES_ORDER_LINE)
        if snap is None:
            return Coverage(None, None, [])
        params = {"ds": snap.dataset_id, "seq": snap.seq}
        r = (await self._c.execute(text(
            f"SELECT min(local_date) AS a, max(local_date) AS b FROM analytics.order_lines"
            f" WHERE {visible()}"), params)).one()
        currencies: list[str] = list((await self._c.execute(text(
            f"SELECT DISTINCT currency FROM analytics.order_lines WHERE {visible()} ORDER BY 1"),
            params)).scalars().all())
        return Coverage(r.a, r.b, [str(c).strip() for c in currencies])


def snapshot_ids(snapshots: dict[Entity, SnapshotRef]) -> list[UUID]:
    return [s.id for s in snapshots.values()]
