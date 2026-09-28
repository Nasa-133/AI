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
    AREA = "area"  # chiziq + to‘ldirilgan maydon (trend hajmi)
    BAR = "bar"  # ko‘p a’zoda UI o‘zi yotiq qiladi (top-N)
    STACKED_BAR = "stacked_bar"  # 2 kesim: X — birinchisi, qatlamlar — ikkinchisi
    PIE = "pie"  # ulushlar (donut): 1 kesim, 1 additiv metrika
    FUNNEL = "funnel"  # voronka: 1 kesim (masalan, CRM bosqichlari)
    HEATMAP = "heatmap"  # 2 kesim, 1 metrika (masalan, filial × oy marjasi)
    TABLE = "table"
    TEXT = "text"


MAX_PIE_SLICES = 12


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


def _real_dimensions(columns: list[dict[str, Any]]) -> list[str]:
    """Kesim ustunlari (nom va valyuta yordamchi ustunlarisiz)."""
    return [c["name"] for c in columns if c["kind"] == "dimension"
            and not str(c["name"]).endswith("_name") and c["name"] != "currency"]


def _values(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in columns if c["kind"] in ("metric", "current")]


def validate_widget(widget: Widget, result: dict[str, Any] | None) -> None:
    """Widget turi natija shakliga mosmi. Model yuborgan raqam emas — faqat natija ID’si."""
    if widget.type is WidgetType.TEXT:
        if not widget.text or widget.query_spec_id is not None:
            raise InvalidDashboard(f"“{widget.title}”: matn widget’ida faqat matn bo‘ladi.")
        return
    if widget.query_spec_id is None or result is None:
        raise InvalidDashboard(f"“{widget.title}”: mavjud query_spec_id kerak.")
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    dims = _real_dimensions(columns)
    values = _values(columns)
    t = widget.type
    problem = None
    if t is WidgetType.KPI and len(rows) != 1:
        problem = "KPI uchun natija bitta qatordan iborat bo‘lsin."
    elif t in (WidgetType.LINE, WidgetType.AREA) and (not dims or dims[0] not in TIME_DIMENSIONS):
        problem = "chiziqli grafik vaqt kesimini talab qiladi."
    elif t is WidgetType.BAR and not dims:
        problem = "ustunli grafik kamida bitta kesim talab qiladi."
    elif t in (WidgetType.STACKED_BAR, WidgetType.HEATMAP) and (len(dims) != 2
                                                               or len(values) != 1):
        problem = "bu grafik ikki kesim va bitta ko‘rsatkichni talab qiladi."
    elif t in (WidgetType.PIE, WidgetType.FUNNEL):
        if len(dims) != 1 or len(values) != 1:
            problem = "ulush/voronka grafigi bitta kesim va bitta ko‘rsatkichni talab qiladi."
        elif values[0].get("unit") == "percent":
            problem = "foiz ko‘rsatkichni ulushlarga bo‘lib bo‘lmaydi — ustunli grafik tanlang."
        elif t is WidgetType.PIE and len(rows) > MAX_PIE_SLICES:
            problem = (f"ulush grafigida ko‘pi bilan {MAX_PIE_SLICES} ta bo‘lak — top-N yoki "
                       "ustunli grafik tanlang.")
    if problem:
        raise InvalidDashboard(f"“{widget.title}”: {problem}")
