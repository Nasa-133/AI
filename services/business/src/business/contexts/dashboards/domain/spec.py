"""DashboardSpec (TZ 8.2): widget faqat saqlangan query natijasiga bog‘lanadi."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from business.kernel.errors import ValidationFailed

TIME_DIMENSIONS = frozenset({"month", "week", "day"})
MAX_WIDGETS = 12


class InvalidDashboard(ValidationFailed):
    code = "INVALID_DASHBOARD"


class WidgetType(StrEnum):
    KPI = "kpi"
    LINE = "line"
    BAR = "bar"
    TABLE = "table"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class Widget:
    id: str
    title: str
    type: WidgetType
    query_spec_id: UUID | None
    text: str | None

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "type": self.type.value,
                "query_spec_id": str(self.query_spec_id) if self.query_spec_id else None,
                "text": self.text}


@dataclass(frozen=True, slots=True)
class DashboardSpec:
    title: str
    description: str | None
    widgets: tuple[Widget, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.title.strip()) <= 200:
            raise InvalidDashboard("Dashboard nomi 1–200 belgi bo‘lishi kerak.")
        if not 1 <= len(self.widgets) <= MAX_WIDGETS:
            raise InvalidDashboard(f"1–{MAX_WIDGETS} ta widget bo‘lishi kerak.")

    def to_json(self) -> dict[str, Any]:
        return {"title": self.title, "description": self.description,
                "widgets": [w.to_json() for w in self.widgets]}


def validate_widget(widget: Widget, result: dict[str, Any] | None) -> None:
    """Widget turi natija shakliga mosmi. Model yuborgan raqam emas — faqat natija ID’si."""
    if widget.type is WidgetType.TEXT:
        if not widget.text or widget.query_spec_id is not None:
            raise InvalidDashboard(f"“{widget.title}”: matn widget’ida faqat matn bo‘ladi.")
        return
    if widget.query_spec_id is None or result is None:
        raise InvalidDashboard(f"“{widget.title}”: mavjud query_spec_id kerak.")
    columns = result.get("columns", [])
    dims = [c["name"] for c in columns if c["kind"] == "dimension"]
    if widget.type is WidgetType.KPI and len(result.get("rows", [])) != 1:
        raise InvalidDashboard(f"“{widget.title}”: KPI uchun natija bitta qatordan iborat bo‘lsin.")
    if widget.type is WidgetType.LINE and (not dims or dims[0] not in TIME_DIMENSIONS):
        raise InvalidDashboard(f"“{widget.title}”: chiziqli grafik vaqt kesimini talab qiladi.")
    if widget.type is WidgetType.BAR and not dims:
        raise InvalidDashboard(f"“{widget.title}”: ustunli grafik kamida bitta kesim talab qiladi.")
