"""Yig‘indi (komponent) so‘rovlari. SQL faqat oq ro‘yxatdagi bo‘laklardan yig‘iladi; qiymatlar
har doim bind parametr. Metrika ma’nosi domain/metrics.py’da."""

from collections import OrderedDict, defaultdict
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
from ..ports.store import ComponentRow, Coverage, Snapshots, SnapshotSet
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


class _SnapshotCache:
    """Snapshot o‘zgarmas (dataset_id + seq): uning qamrovi va nomlar lug‘ati bir marta hisoblanadi.

    Yangi snapshot — yangi kalit, shuning uchun eskirgan qiymat qaytmaydi. Kalitda tenant ham bor;
    qiymat har doim tenant RLS kontekstida hisoblangan. Hajmi cheklangan (LRU).
    """

    def __init__(self, size: int = 512) -> None:
        self._data: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
        self._size = size

    def get(self, key: tuple[Any, ...]) -> Any:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key: tuple[Any, ...], value: Any) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._size:
            self._data.popitem(last=False)


SNAPSHOT_CACHE = _SnapshotCache()


def visible_any(parts: SnapshotSet, params: dict[str, Any]) -> str:
    """Bir nechta manba snapshot’lari (har biri o‘z `seq` holatida) — yig‘indi birlashadi."""
    clauses = []
    for i, snap in enumerate(parts):
        params[f"p{i}_ds"], params[f"p{i}_seq"] = snap.dataset_id, snap.seq
        clauses.append(f"({visible(prefix=f'p{i}_')})")
    return "(" + " OR ".join(clauses) + ")" if clauses else "false"


def _parts_key(parts: SnapshotSet) -> tuple[tuple[UUID, int], ...]:
    return tuple(sorted((p.dataset_id, p.seq) for p in parts))


class SqlAggregates:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID | None = None) -> None:
        self._c = conn
        self._cache_tenant = tenant_id

    async def _sums(self, table: str, snapshot: SnapshotSet, sums: dict[C, str],
                    spec: QuerySpec, period: Period, dims: tuple[D, ...],
                    where_extra: str = "") -> list[tuple[tuple[str, ...], dict[C, Decimal]]]:
        groups = _group_exprs(dims)
        params: dict[str, Any] = {"start": period.start, "end": period.end}
        where = (f"{visible_any(snapshot, params)} AND status = 'confirmed'"
                 " AND local_date BETWEEN :start AND :end"
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
                               snapshots: Snapshots,
                               dimensions: tuple[D, ...]) -> list[ComponentRow]:
        merged: dict[tuple[str, ...], dict[C, Decimal]] = defaultdict(dict)
        parts = [(Entity.SALES_ORDER_LINE, "analytics.order_lines", _ORDER_SUMS),
                 (Entity.SALES_RETURN, "analytics.returns", _RETURN_SUMS)]
        for entity, table, sums in parts:
            snap = snapshots.get(entity)
            if not snap:
                continue
            for key, values in await self._sums(table, snap, sums, spec, period, dimensions):
                merged[key].update(values)
        return [ComponentRow(k, v) for k, v in sorted(merged.items())]

    async def receivable_components(self, spec: QuerySpec, as_of: date, snapshot: SnapshotSet,
                                    dimensions: tuple[D, ...]) -> list[ComponentRow]:
        groups = [*(_DIM_SQL[d] for d in dimensions if d is not D.CURRENCY), "currency"]
        params: dict[str, Any] = {"as_of": as_of}
        where = (f"{visible_any(snapshot, params)} AND issued_on <= :as_of"
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
                              snapshots: Snapshots) -> dict[str, str]:
        snap = snapshots.get(Entity.SALES_ORDER_LINE)
        if dimension not in _NAME_SQL or not snap or not codes:
            return {}
        code_col, name_col, table = _NAME_SQL[dimension]
        key = (self._cache_tenant, "names", dimension.value, _parts_key(snap))
        names: dict[str, str] | None = SNAPSHOT_CACHE.get(key)
        if names is None:
            # Butun snapshot lug‘ati bir marta (kod ustunida indeks yo‘q — har so‘rovda skan emas).
            params: dict[str, Any] = {}
            where = visible_any(snap, params)
            rows = (await self._c.execute(text(
                f"SELECT {code_col} AS code, max({name_col}) AS name FROM {table}"
                f" WHERE {where} GROUP BY 1"), params)).all()
            names = {r.code: r.name for r in rows if r.name}
            SNAPSHOT_CACHE.put(key, names)
        return {c: names[c] for c in codes if c in names}

    async def coverage(self, snapshots: Snapshots) -> Coverage:
        snap = snapshots.get(Entity.SALES_ORDER_LINE)
        if not snap:
            return Coverage(None, None, [])
        key = (self._cache_tenant, "coverage", _parts_key(snap))
        cached: Coverage | None = SNAPSHOT_CACHE.get(key)
        if cached is not None:
            return cached
        params: dict[str, Any] = {}
        where = visible_any(snap, params)
        r = (await self._c.execute(text(
            f"SELECT min(local_date) AS a, max(local_date) AS b FROM analytics.order_lines"
            f" WHERE {where}"), params)).one()
        currencies: list[str] = list((await self._c.execute(text(
            f"SELECT DISTINCT currency FROM analytics.order_lines WHERE {where} ORDER BY 1"),
            params)).scalars().all())
        coverage = Coverage(r.a, r.b, [str(c).strip() for c in currencies])
        SNAPSHOT_CACHE.put(key, coverage)
        return coverage


def snapshot_ids(snapshots: Snapshots) -> list[UUID]:
    return [s.id for parts in snapshots.values() for s in parts]
