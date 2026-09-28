"""Vizual widget turlari natija shakliga mos kelishi (Power BI/Superset uslubidagi grafiklar)."""

from typing import Any
from uuid import uuid4

import pytest

from business.contexts.dashboards.domain.spec import (
    InvalidDashboard,
    Widget,
    WidgetType,
    validate_widget,
)


def result(dims: list[str], metrics: list[tuple[str, str]], rows: int) -> dict[str, Any]:
    columns = [*({"name": d, "kind": "dimension"} for d in dims),
               *({"name": m, "kind": "metric", "metric_id": m, "unit": u} for m, u in metrics)]
    return {"columns": columns, "rows": [["x"] * len(columns)] * rows}


def check(kind: WidgetType, data: dict[str, Any]) -> None:
    validate_widget(Widget("w1", "Sinov", kind, uuid4(), None), data)


def test_charts_accept_matching_shapes() -> None:
    check(WidgetType.AREA, result(["month"], [("net_sales", "money")], 12))
    check(WidgetType.STACKED_BAR, result(["month", "branch", "branch_name"],
                                         [("net_sales", "money")], 20))
    check(WidgetType.HEATMAP, result(["month", "branch"], [("gross_margin", "percent")], 30))
    check(WidgetType.PIE, result(["channel"], [("crm_deals_won", "count")], 5))
    check(WidgetType.FUNNEL, result(["stage"], [("crm_pipeline_open", "money")], 4))
    check(WidgetType.BAR, result(["product", "product_name"], [("net_sales", "money")], 40))


@pytest.mark.parametrize(("kind", "data", "message"), [
    (WidgetType.AREA, result(["branch"], [("net_sales", "money")], 5), "vaqt"),
    (WidgetType.STACKED_BAR, result(["branch"], [("net_sales", "money")], 5), "ikki kesim"),
    (WidgetType.HEATMAP, result(["month", "branch"], [("net_sales", "money"),
                                                     ("returns", "money")], 5), "bitta"),
    (WidgetType.PIE, result(["branch"], [("gross_margin", "percent")], 5), "foiz"),
    (WidgetType.PIE, result(["product"], [("net_sales", "money")], 40), "12"),
    (WidgetType.FUNNEL, result([], [("net_sales", "money")], 1), "bitta kesim"),
])
def test_charts_reject_wrong_shapes(kind: WidgetType, data: dict[str, Any], message: str) -> None:
    with pytest.raises(InvalidDashboard, match=message):
        check(kind, data)
