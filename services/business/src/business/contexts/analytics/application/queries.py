"""run_metric_query va list_available_metrics (TZ 7.2): deterministik hisob, natija saqlanadi."""

from dataclasses import dataclass, replace
from datetime import date
from typing import Any
from uuid import UUID, uuid4

from business.kernel.errors import BusinessError

from ..domain.ingestion import Entity
from ..domain.metrics import CATALOG, DIMENSION_NAMES, Dimension, Subject
from ..domain.query import Filters, Period, QuerySpec
from ..ports.store import AnalyticsStore, ComponentRow, Snapshots, StoredQuery, snapshot_list
from . import results as R

_ENTITY_LABEL = {Entity.SALES_ORDER_LINE: "Savdo", Entity.FINANCE_RECEIVABLE: "Debitorlik"}


class NoData(BusinessError):
    code = "NO_DATA"


class SettingsNotApproved(BusinessError):
    code = "METRIC_SETTINGS_NOT_APPROVED"


class QueryNotFound(BusinessError):
    code = "NOT_FOUND"


class BranchForbidden(BusinessError):
    code = "BRANCH_FORBIDDEN"


@dataclass(frozen=True, slots=True)
class QueryContext:
    user_id: UUID
    task_id: UUID | None
    today: date
    timezone: str
    # S02: foydalanuvchiga ruxsat etilgan filiallar; None — barchasi.
    branch_scope: tuple[str, ...] | None = None


def apply_branch_scope(spec: QuerySpec,
                       scope: tuple[str, ...] | None) -> tuple[QuerySpec, str | None]:
    """S02: filtr ruxsat etilgan filiallar bilan cheklanadi; ruxsatsiz filial so‘ralsa — rad.

    Filtrsiz (umumiy) so‘rov jimgina qisqartirilmaydi: natijaga cheklov izohi qo‘shiladi.
    """
    if scope is None:
        return spec, None
    if not scope:
        raise BranchForbidden("Sizga hech bir filial ma’lumoti ruxsat etilmagan.")
    requested = spec.filters.branch_codes
    if requested:
        denied = [b for b in requested if b not in scope]
        if denied:
            raise BranchForbidden("Bu filial(lar) ma’lumoti sizga ruxsat etilmagan: "
                                  + ", ".join(denied) + ".")
        allowed = requested
    else:
        allowed = scope
    note = "Faqat ruxsat etilgan filiallar: " + ", ".join(allowed) + "."
    return replace(spec, filters=replace(spec.filters, branch_codes=tuple(allowed))), note


def spec_from_args(a: dict[str, Any]) -> QuerySpec:
    f = a.get("filters") or {}
    return QuerySpec(
        metric_ids=tuple(a["metric_ids"]),
        period=Period(date.fromisoformat(a["date_range"]["from"]),
                      date.fromisoformat(a["date_range"]["to"])),
        dimensions=tuple(Dimension(d) for d in a.get("dimensions") or []),
        filters=Filters(*(tuple(f[k]) if f.get(k) else None
                          for k in ("branch_codes", "product_codes", "customer_codes"))),
        currency=a.get("currency"),
        limit=a.get("limit") or 500,
    )


def source_refs(snapshots: Snapshots, query_id: UUID) -> list[dict[str, Any]]:
    refs = [{"kind": "dataset_snapshot", "id": str(s.id), "version_id": None,
             "locator": e.value} for e, parts in snapshots.items() for s in parts]
    return [*refs, {"kind": "query_result", "id": str(query_id), "version_id": None,
                    "locator": None}]


class QueryService:
    def __init__(self, store: AnalyticsStore) -> None:
        self._s = store

    @property
    def store(self) -> AnalyticsStore:
        return self._s

    async def list_metrics(self, ctx: QueryContext, subject: str) -> dict[str, Any]:
        settings = await self._s.metric_settings()
        snaps = await self._s.active_snapshots()
        cov = await self._s.coverage(snaps)
        return {
            "timezone": ctx.timezone, "today": ctx.today.isoformat(), "currencies": cov.currencies,
            "data_coverage": {"from": cov.first_day.isoformat() if cov.first_day else None,
                              "to": cov.last_day.isoformat() if cov.last_day else None},
            "metrics": [{"id": m.id, "name": m.name, "description": m.description,
                         "unit": m.unit.value, "version": m.version, "subject": m.subject.value,
                         "dimensions": [d.value for d in m.dimensions],
                         "approved": settings is not None}
                        for m in CATALOG.values()
                        if subject == "all" or m.subject is Subject(subject)],
            "dimensions": [{"id": d.value, "name": n} for d, n in DIMENSION_NAMES.items()],
        }

    async def require_ready(self, spec: QuerySpec,
                            snapshots: Snapshots | None = None,
                            ) -> Snapshots:
        if await self._s.metric_settings() is None:
            raise SettingsNotApproved(
                "Hisob qoidalari (QQS, qaytarish, chegirma) hali tasdiqlanmagan, shuning uchun "
                "moliyaviy raqam chiqarilmaydi. Korxona egasi yoki administrator: Sozlamalar → "
                "Hisob qoidalari → “Tasdiqlash”.")
        snaps = snapshots if snapshots is not None else await self._s.active_snapshots()
        needed = (Entity.FINANCE_RECEIVABLE if spec.is_receivable else Entity.SALES_ORDER_LINE)
        if not snaps.get(needed):
            raise NoData(f"{_ENTITY_LABEL.get(needed, needed.value)} ma’lumoti hali yuklanmagan. "
                         "Integratsiyalar sahifasida ERP’ni ulang yoki CSV fayl yuklang.")
        keep = ({Entity.FINANCE_RECEIVABLE} if spec.is_receivable
                else {Entity.SALES_ORDER_LINE, Entity.SALES_RETURN})
        return {e: s for e, s in snaps.items() if e in keep}

    async def components(self, spec: QuerySpec, period: Period,
                         snaps: Snapshots,
                         dims: tuple[Dimension, ...]) -> list[ComponentRow]:
        if spec.is_receivable:
            return await self._s.receivable_components(
                spec, period.end, snaps[Entity.FINANCE_RECEIVABLE], dims)
        return await self._s.sales_components(spec, period, snaps, dims)

    async def names(self, rows: list[ComponentRow], dims: tuple[Dimension, ...],
                    snaps: Snapshots) -> dict[Dimension, dict[str, str]]:
        plain = [d for d in dims if d is not Dimension.CURRENCY]
        out: dict[Dimension, dict[str, str]] = {}
        for i, d in enumerate(plain):
            if d in R.NAMED:
                out[d] = await self._s.dimension_names(d, sorted({r.key[i] for r in rows}), snaps)
        return out

    async def run(self, ctx: QueryContext, args: dict[str, Any]) -> tuple[dict[str, Any],
                                                                          list[dict[str, Any]]]:
        spec, scope_note = apply_branch_scope(spec_from_args(args), ctx.branch_scope)
        snaps = await self.require_ready(spec)
        rows = await self.components(spec, spec.period, snaps, spec.dimensions)
        currencies = sorted({r.key[-1] for r in rows})
        with_currency = spec.currency is None and (len(currencies) > 1
                                                   or Dimension.CURRENCY in spec.dimensions)
        names = await self.names(rows, spec.dimensions, snaps)
        defs = spec.definitions
        out_rows, notes = [], []
        for r in rows[: spec.limit]:
            cells, metric_notes = R.metric_cells(r.values, defs)
            out_rows.append([*R.dimension_cells(r.key, spec.dimensions, with_currency, names),
                             *cells])
            notes.extend(metric_notes)
        if len(currencies) > 1 and spec.currency is None:
            notes.append("Bir nechta valyuta: natija valyuta bo‘yicha ajratilgan, qo‘shilmagan.")
        if spec.period.is_incomplete(ctx.today):
            notes.append("Davr hali tugamagan — to‘liq davr bilan izohsiz solishtirmang.")
        if not spec.is_receivable and not snaps.get(Entity.SALES_RETURN):
            notes.append("Qaytarishlar ma’lumoti yuklanmagan — sof savdoga ta’sir qilishi mumkin.")
        if scope_note:
            notes.append(scope_note)
        query_id = uuid4()
        data = {
            "query_spec_id": str(query_id),
            "dataset_snapshot_ids": [str(s.id) for s in snapshot_list(snaps)],
            "metric_versions": [{"metric_id": d.id, "version": d.version} for d in defs],
            "period": {"from": spec.period.start.isoformat(), "to": spec.period.end.isoformat()},
            "currency": spec.currency or (currencies[0] if len(currencies) == 1 else None),
            "columns": [*R.dimension_columns(spec.dimensions, with_currency),
                        *({"name": d.id, "kind": "metric", "metric_id": d.id, "unit": d.unit.value}
                          for d in defs)],
            "rows": out_rows, "row_count": len(out_rows), "truncated": len(rows) > spec.limit,
            "as_of": max(s.as_of for s in snapshot_list(snaps)).isoformat(),
            "notes": list(dict.fromkeys(notes)),
        }
        # Saqlangan spec’da amaldagi filial filtri — dashboard/yangilash doirani saqlaydi.
        stored_args = (args if scope_note is None else
                       {**args, "filters": {**(args.get("filters") or {}),
                                            "branch_codes": list(spec.filters.branch_codes or ())}})
        await self._s.save_query(StoredQuery(query_id, "query", stored_args,
                                             [s.id for s in snapshot_list(snaps)], data,
                                             ctx.user_id, ctx.task_id))
        return data, source_refs(snaps, query_id)


async def rerun_stored(service: QueryService, ctx: QueryContext, query_id: UUID) -> UUID | None:
    """Dashboard yangilash uchun: faqat oddiy query (taqqoslash/hissa emas) qayta hisoblanadi."""
    stored = await service.store.get_query(query_id)
    if stored is None or stored.kind != "query":
        return None
    data, _ = await service.run(ctx, stored.spec)
    return UUID(data["query_spec_id"])
