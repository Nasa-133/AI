"""compare_periods va explain_contributions — asosiy query snapshot’lari bilan (bir xil raqam)."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from ..domain.metrics import ADDITIVE_METRICS, CATALOG, Dimension, Unit, compute, contributions
from ..domain.metrics import growth as growth_of
from ..domain.query import InvalidQuery, Period, QuerySpec
from ..ports.store import ComponentRow, StoredQuery, snapshot_list
from . import results as R
from .queries import (
    QueryContext,
    QueryNotFound,
    QueryService,
    apply_branch_scope,
    source_refs,
    spec_from_args,
)


def _period(p: dict[str, str]) -> Period:
    return Period(date.fromisoformat(p["from"]), date.fromisoformat(p["to"]))


def _pdict(p: Period) -> dict[str, str]:
    return {"from": p.start.isoformat(), "to": p.end.isoformat()}


class ComparisonService:
    def __init__(self, queries: QueryService) -> None:
        self._q = queries

    async def _base(self, ctx: QueryContext,
                    query_spec_id: str) -> tuple[StoredQuery, QuerySpec, str | None]:
        base = await self._q.store.get_query(UUID(query_spec_id))
        if base is None or base.kind != "query":
            raise QueryNotFound("query_spec_id topilmadi (avval run_metric_query chaqiring).")
        # Boshqa foydalanuvchining so‘rovi ham joriy foydalanuvchi doirasida tekshiriladi (S02).
        spec, note = apply_branch_scope(spec_from_args(base.spec), ctx.branch_scope)
        return base, spec, note

    async def compare(self, ctx: QueryContext, args: dict[str, Any]) -> tuple[dict[str, Any],
                                                                              list[dict[str, Any]]]:
        base, spec, scope_note = await self._base(ctx, args["query_spec_id"])
        comparison = _period(args["comparison_range"])
        snaps = await self._q.require_ready(
            spec, await self._q.store.snapshots_by_ids(base.snapshot_ids))
        current = {r.key: r.values for r in await self._q.components(
            spec, spec.period, snaps, spec.dimensions)}
        previous = {r.key: r.values for r in await self._q.components(
            spec, comparison, snaps, spec.dimensions)}
        keys = sorted(set(current) | set(previous))
        currencies = sorted({k[-1] for k in keys})
        with_currency = spec.currency is None and (len(currencies) > 1
                                                   or Dimension.CURRENCY in spec.dimensions)
        rows_as_components = [ComponentRow(k, {}) for k in keys]  # nomlar uchun
        names = await self._q.names(rows_as_components, spec.dimensions, snaps)
        columns = R.dimension_columns(spec.dimensions, with_currency)
        for d in spec.definitions:
            for kind in ("current", "previous", "abs_change", "pct_change"):
                unit = "percent" if kind == "pct_change" else d.unit.value
                columns.append({"name": f"{d.id}__{kind}", "kind": kind, "metric_id": d.id,
                                "unit": unit})
        rows, notes = [], []
        # Butun davrda birorta yozuv bo‘lmasa — bu “nol” emas, ma’lumot yo‘q: qiymat bo‘sh qoladi.
        # (Ma’lumot bor davrda a’zoning yozuvi bo‘lmasa — haqiqiy nol.)
        if not current:
            notes.append(f"Joriy davr ({spec.period.start} — {spec.period.end}) uchun ma’lumot "
                         "yo‘q — nol deb hisoblanmadi.")
        if not previous:
            notes.append(f"Oldingi davr ({comparison.start} — {comparison.end}) uchun ma’lumot "
                         "yo‘q — nol deb hisoblanmadi.")
        for k in keys:
            cells = R.dimension_cells(k, spec.dimensions, with_currency, names)
            label = " / ".join(x for x in k if x)
            for d in spec.definitions:
                cur = compute(d.id, current.get(k, {})).value if current else None
                prev = compute(d.id, previous.get(k, {})).value if previous else None
                if cur is None or prev is None:
                    cells += [R.fmt(cur, d.unit), R.fmt(prev, d.unit), None, None]
                    continue
                if d.unit is Unit.PERCENT:
                    # Nisbat uchun foiz o‘zgarishi emas, foiz punkti farqi ko‘rsatiladi.
                    cells += [R.fmt(cur, d.unit), R.fmt(prev, d.unit),
                              R.fmt(cur - prev, d.unit), None]
                    continue
                g = growth_of(cur, prev)
                if g.note:
                    notes.append(f"{label}: {g.note}")
                cells += [R.fmt(cur, d.unit), R.fmt(prev, d.unit), R.fmt(g.absolute, d.unit),
                          R.fmt(g.pct, Unit.PERCENT)]
            rows.append(cells)
        if scope_note:
            notes.append(scope_note)
        query_id = uuid4()
        data = {"query_spec_id": str(query_id), "base_query_spec_id": str(base.id),
                "current_period": _pdict(spec.period), "comparison_period": _pdict(comparison),
                "currency": spec.currency or (currencies[0] if len(currencies) == 1 else None),
                "dataset_snapshot_ids": [str(s.id) for s in snapshot_list(snaps)],
                "columns": columns, "rows": rows, "notes": list(dict.fromkeys(notes))}
        await self._q.store.save_query(StoredQuery(
            query_id, "comparison", args, base.snapshot_ids, data, ctx.user_id, ctx.task_id))
        return data, source_refs(snaps, query_id)

    async def explain(self, ctx: QueryContext, args: dict[str, Any]) -> tuple[dict[str, Any],
                                                                              list[dict[str, Any]]]:
        base, spec, scope_note = await self._base(ctx, args["query_spec_id"])
        metric_id, dim = args["metric_id"], Dimension(args["dimension"])
        if metric_id not in ADDITIVE_METRICS:
            raise InvalidQuery(f"“{metric_id}” nisbat metrikasi — hissaga ajratib bo‘lmaydi. "
                               "Uning tarkibiy qismlarini (masalan, yalpi foyda) tahlil qiling.")
        if metric_id not in CATALOG or dim not in CATALOG[metric_id].dimensions:
            raise InvalidQuery("Metrika yoki o‘lcham mos emas.")
        comparison = _period(args["comparison_range"])
        snaps = await self._q.require_ready(
            spec, await self._q.store.snapshots_by_ids(base.snapshot_ids))
        dims = (dim,) if dim is not Dimension.CURRENCY else ()
        cur_rows = await self._q.components(spec, spec.period, snaps, dims)
        prev_rows = await self._q.components(spec, comparison, snaps, dims)
        currencies = sorted({r.key[-1] for r in cur_rows + prev_rows})
        currency = spec.currency or (currencies[0] if len(currencies) == 1 else None)
        if currency is None:
            raise InvalidQuery("Bir nechta valyuta: hissani hisoblash uchun valyutani tanlang.")

        def by_member(rows: list[ComponentRow]) -> dict[str, Decimal]:
            return {r.key[0]: compute(metric_id, r.values).value or Decimal(0)
                    for r in rows if r.key[-1] == currency}

        names = await self._q.names(cur_rows + prev_rows, dims, snaps)
        total, items = contributions(by_member(cur_rows), by_member(prev_rows))
        unit = CATALOG[metric_id].unit

        def label(code: str) -> str:
            name = names.get(dim, {}).get(code)
            return f"{code} ({name})" if name else code

        data = {
            "metric_id": metric_id, "dimension": dim.value, "current_period": _pdict(spec.period),
            "comparison_period": _pdict(comparison), "currency": currency,
            "total_current": R.fmt(sum((i.current for i in items), Decimal(0)), unit),
            "total_previous": R.fmt(sum((i.previous for i in items), Decimal(0)), unit),
            "total_change": R.fmt(total, unit),
            "contributions": [{"member": label(i.member), "current": R.fmt(i.current, unit),
                               "previous": R.fmt(i.previous, unit),
                               "change": R.fmt(i.change, unit),
                               "share_of_change_pct": R.fmt(i.share_of_change_pct, Unit.PERCENT)}
                              for i in items],
            "dataset_snapshot_ids": [str(s.id) for s in snapshot_list(snaps)],
            "notes": ["Hisobiy hissa: har a’zoning umumiy o‘zgarishdagi ulushi. Bu sababni "
                      "isbotlamaydi (TZ 7.3).", *([scope_note] if scope_note else [])],
        }
        query_id = uuid4()
        await self._q.store.save_query(StoredQuery(
            query_id, "contribution", args, base.snapshot_ids, data, ctx.user_id, ctx.task_id))
        return data, source_refs(snaps, query_id)
