"""Dashboard: yaratish, doska, tafsilot, tahrir/versiya, ulashish, yangilash, CSV eksport (TZ 8).

Har amalda ACL tekshiriladi (TZ 3); ruxsatsiz dashboard mavjudligi oshkor qilinmaydi (404).
Doska va tafsilot OpenAI chaqirmaydi — saqlangan natijalar o‘qiladi.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from business.kernel.errors import BusinessError

from ..domain.access import (
    MANAGERS,
    DashboardForbidden,
    Visibility,
    can_edit,
    can_view,
    csv_safe,
    within_branch_scope,
)
from ..domain.edit import apply_edit
from ..domain.spec import DashboardSpec, Widget, WidgetType, validate_widget
from ..ports.store import DashboardRecord, DashboardStore, QueryRefresher, QueryResults


class DashboardNotFound(BusinessError):
    code = "NOT_FOUND"


@dataclass(frozen=True, slots=True)
class Viewer:
    user_id: UUID
    role: str
    # S02: None — barcha filiallar.
    branch_scope: tuple[str, ...] | None = None


class DashboardService:
    def __init__(self, store: DashboardStore, results: QueryResults,
                 refresher: QueryRefresher | None = None) -> None:
        self._store = store
        self._results = results
        self._refresher = refresher

    async def create(self, *, user_id: UUID, task_id: UUID | None, title: str,
                     description: str | None, widgets: list[dict[str, Any]],
                     branch_scope: tuple[str, ...] | None = None) -> DashboardRecord:
        spec = DashboardSpec(title.strip(), description, tuple(
            Widget(f"w{i + 1}", w["title"], WidgetType(w["type"]),
                   UUID(w["query_spec_id"]) if w.get("query_spec_id") else None, w.get("text"))
            for i, w in enumerate(widgets)))
        for widget in spec.widgets:
            if widget.query_spec_id and not await self._allowed(branch_scope,
                                                                widget.query_spec_id):
                raise DashboardForbidden("Widget ruxsat etilmagan filial ma’lumotiga tayanadi.")
        await self._validate(spec)
        return await self._store.create(uuid4(), spec, user_id=user_id, task_id=task_id)

    async def replace(self, viewer: Viewer, dashboard_id: UUID, *, title: str,
                      description: str | None, widgets: list[dict[str, Any]]) -> DashboardRecord:
        """Tarkibni yangilash (tahlil qayta hisoblanganda) — yangi versiya, tarix qoladi."""
        await self._editable(viewer, dashboard_id)
        spec = DashboardSpec(title.strip(), description, tuple(
            Widget(f"w{i + 1}", w["title"], WidgetType(w["type"]),
                   UUID(w["query_spec_id"]) if w.get("query_spec_id") else None, w.get("text"))
            for i, w in enumerate(widgets)))
        await self._validate(spec)
        return await self._store.add_version(dashboard_id, spec, user_id=viewer.user_id)

    async def cards(self, viewer: Viewer, *, limit: int = 50,
                    query: str | None = None) -> list[dict[str, Any]]:
        """Doska kartochkalari: saqlangan natijadan preview (qayta hisob va LLM yo‘q)."""
        cards = []
        for d in await self._store.list_visible(limit=limit, query=query, user_id=viewer.user_id,
                                        see_all=viewer.role in MANAGERS):
            preview = await self._preview(d, viewer.branch_scope)
            cards.append({"id": str(d.id), "title": d.spec["title"], "version": d.version,
                          "updated_at": d.updated_at.isoformat(),
                          "visibility": d.visibility.value, **preview})
        return cards

    async def detail(self, viewer: Viewer, dashboard_id: UUID) -> dict[str, Any]:
        d = await self._visible(viewer, dashboard_id)
        widgets = []
        for w in d.spec["widgets"]:
            qid = w["query_spec_id"]
            if qid and not await self._allowed(viewer.branch_scope, UUID(qid)):
                # S02: ruxsatsiz filial raqamlari ko‘rsatilmaydi, widget borligi esa ko‘rinadi.
                widgets.append({**w, "data": None, "query": None, "status": "restricted"})
                continue
            data = await self._results.result(UUID(qid)) if qid else None
            spec = await self._results.spec(UUID(qid)) if qid else None
            status = "ready" if data or w["text"] else "missing"
            widgets.append({**w, "data": data, "query": spec, "status": status})
        return {"id": str(d.id), "title": d.spec["title"], "description": d.spec["description"],
                "version": d.version, "updated_at": d.updated_at.isoformat(), "widgets": widgets,
                "visibility": d.visibility.value,
                "shared_with": sorted(str(u) for u in d.shared_with),
                "can_edit": can_edit(d.access, viewer.user_id, viewer.role)}

    async def edit(self, viewer: Viewer, dashboard_id: UUID, *, title: str | None,
                   description: str | None,
                   widgets: list[dict[str, Any]] | None) -> DashboardRecord:
        d = await self._editable(viewer, dashboard_id)
        spec = apply_edit(d.spec, title=title, description=description, widgets=widgets)
        await self._validate(spec)
        return await self._store.add_version(dashboard_id, spec, user_id=viewer.user_id)

    async def versions(self, viewer: Viewer, dashboard_id: UUID) -> list[dict[str, Any]]:
        await self._visible(viewer, dashboard_id)
        return [{"version": v.version, "title": v.title, "created_by": str(v.created_by),
                 "created_at": v.created_at.isoformat()}
                for v in await self._store.versions(dashboard_id)]

    async def share(self, viewer: Viewer, dashboard_id: UUID, visibility: str,
                    user_ids: list[UUID]) -> None:
        """Ulashish ro‘yxatidagi foydalanuvchilar korxona a’zosi ekanini chaqiruvchi tekshiradi."""
        await self._editable(viewer, dashboard_id)
        await self._store.set_access(dashboard_id, Visibility(visibility), frozenset(user_ids),
                                     user_id=viewer.user_id)

    async def refresh(self, viewer: Viewer, dashboard_id: UUID) -> dict[str, Any]:
        """Har widget so‘rovini oxirgi snapshot bilan qayta hisoblash → yangi versiya."""
        d = await self._editable(viewer, dashboard_id)
        assert self._refresher is not None
        refreshed, skipped = [], []
        for w in d.spec["widgets"]:
            if w["query_spec_id"] and not await self._allowed(viewer.branch_scope,
                                                              UUID(w["query_spec_id"])):
                skipped.append(w["title"])
                refreshed.append(w)
                continue
            new_id = await self._refresher.rerun(UUID(w["query_spec_id"])) if w[
                "query_spec_id"] else None
            if w["query_spec_id"] and new_id is None:
                skipped.append(w["title"])
            refreshed.append({**w, "query_spec_id": str(new_id) if new_id else w["query_spec_id"]})
        spec = DashboardSpec(d.spec["title"], d.spec["description"], tuple(
            Widget(w["id"], w["title"], WidgetType(w["type"]),
                   UUID(w["query_spec_id"]) if w["query_spec_id"] else None, w["text"])
            for w in refreshed))
        record = await self._store.add_version(dashboard_id, spec, user_id=viewer.user_id)
        return {"version": record.version, "not_refreshed": skipped}

    async def export_csv(self, viewer: Viewer, dashboard_id: UUID,
                         widget_id: str) -> tuple[str, list[list[str]]]:
        """Eksportning o‘zi ham ACL’dan o‘tadi (TZ 8.2); formula injection neytrallanadi."""
        d = await self._visible(viewer, dashboard_id)
        widget = next((w for w in d.spec["widgets"] if w["id"] == widget_id), None)
        if widget is None or not widget["query_spec_id"]:
            raise DashboardNotFound("Eksport qilinadigan widget topilmadi.")
        if not await self._allowed(viewer.branch_scope, UUID(widget["query_spec_id"])):
            raise DashboardForbidden("Bu widget ruxsat etilmagan filial ma’lumotini "
                                     "o‘z ichiga oladi.")
        data = await self._results.result(UUID(widget["query_spec_id"]))
        if data is None:
            raise DashboardNotFound("Widget natijasi topilmadi.")
        rows = [[csv_safe(c["name"]) for c in data["columns"]]]
        rows += [[csv_safe(v) for v in row] for row in data["rows"]]
        return f"{d.spec['title'][:80]} — {widget['title'][:60]}.csv", rows

    async def _validate(self, spec: DashboardSpec) -> None:
        for widget in spec.widgets:
            result = (await self._results.result(widget.query_spec_id)
                      if widget.query_spec_id else None)
            validate_widget(widget, result)

    async def _visible(self, viewer: Viewer, dashboard_id: UUID) -> DashboardRecord:
        d = await self._store.get(dashboard_id)
        if d is None or not can_view(d.access, viewer.user_id, viewer.role):
            raise DashboardNotFound("Dashboard topilmadi.")
        return d

    async def _editable(self, viewer: Viewer, dashboard_id: UUID) -> DashboardRecord:
        d = await self._visible(viewer, dashboard_id)
        if not can_edit(d.access, viewer.user_id, viewer.role):
            raise DashboardForbidden("Bu dashboardni tahrirlash huquqi yo‘q.")
        return d

    async def _allowed(self, scope: tuple[str, ...] | None, query_id: UUID) -> bool:
        return scope is None or within_branch_scope(scope,
                                                    await self._results.branch_filter(query_id))

    async def _preview(self, d: DashboardRecord,
                       scope: tuple[str, ...] | None = None) -> dict[str, Any]:
        for w in d.spec["widgets"]:
            if not w["query_spec_id"]:
                continue
            if not await self._allowed(scope, UUID(w["query_spec_id"])):
                return {"period": None, "kpi": None, "status": "restricted"}
            data = await self._results.result(UUID(w["query_spec_id"]))
            if not data:
                return {"period": None, "kpi": None, "status": "missing"}
            period = data.get("period") or data.get("current_period")
            metric_cols = [i for i, c in enumerate(data["columns"])
                           if c["kind"] in ("metric", "current")]
            kpi = None
            # KPI faqat bitta qatorli natijada; aks holda majburan son qo‘yilmaydi (TZ 6).
            if len(data["rows"]) == 1 and metric_cols:
                i = metric_cols[0]
                kpi = {"metric_id": data["columns"][i]["metric_id"],
                       "value": data["rows"][0][i], "unit": data["columns"][i]["unit"],
                       "currency": data.get("currency")}
            return {"period": period, "kpi": kpi, "status": "ready"}
        return {"period": None, "kpi": None, "status": "ready"}
