"""Dashboard yaratish, doska kartochkalari va tafsilot (TZ 8). OpenAI chaqirilmaydi."""

from typing import Any
from uuid import UUID, uuid4

from business.kernel.errors import BusinessError

from ..domain.spec import DashboardSpec, Widget, WidgetType, validate_widget
from ..ports.store import DashboardRecord, DashboardStore, QueryResults


class DashboardNotFound(BusinessError):
    code = "NOT_FOUND"


class DashboardService:
    def __init__(self, store: DashboardStore, results: QueryResults) -> None:
        self._store = store
        self._results = results

    async def create(self, *, user_id: UUID, task_id: UUID | None, title: str,
                     description: str | None, widgets: list[dict[str, Any]]) -> DashboardRecord:
        spec = DashboardSpec(title.strip(), description, tuple(
            Widget(f"w{i + 1}", w["title"], WidgetType(w["type"]),
                   UUID(w["query_spec_id"]) if w.get("query_spec_id") else None, w.get("text"))
            for i, w in enumerate(widgets)))
        for widget in spec.widgets:
            result = (await self._results.result(widget.query_spec_id)
                      if widget.query_spec_id else None)
            validate_widget(widget, result)
        return await self._store.create(uuid4(), spec, user_id=user_id, task_id=task_id)

    async def cards(self, *, limit: int = 50, query: str | None = None) -> list[dict[str, Any]]:
        """Doska kartochkalari: saqlangan natijadan preview (qayta hisob va LLM yo‘q)."""
        cards = []
        for d in await self._store.list(limit=limit, query=query):
            preview = await self._preview(d)
            cards.append({"id": str(d.id), "title": d.spec["title"], "version": d.version,
                          "updated_at": d.updated_at.isoformat(), **preview})
        return cards

    async def detail(self, dashboard_id: UUID) -> dict[str, Any]:
        d = await self._store.get(dashboard_id)
        if d is None:
            raise DashboardNotFound("Dashboard topilmadi.")
        widgets = []
        for w in d.spec["widgets"]:
            qid = w["query_spec_id"]
            data = await self._results.result(UUID(qid)) if qid else None
            status = "ready" if data or w["text"] else "missing"
            widgets.append({**w, "data": data, "status": status})
        return {"id": str(d.id), "title": d.spec["title"], "description": d.spec["description"],
                "version": d.version, "updated_at": d.updated_at.isoformat(), "widgets": widgets}

    async def _preview(self, d: DashboardRecord) -> dict[str, Any]:
        for w in d.spec["widgets"]:
            if not w["query_spec_id"]:
                continue
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
