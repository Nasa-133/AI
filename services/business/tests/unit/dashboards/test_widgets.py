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


def test_card_spark_only_from_clean_time_series() -> None:
    from business.contexts.dashboards.application.service import _spark

    def col(name: str, kind: str = "dimension") -> dict[str, object]:
        return {"name": name, "kind": kind, "metric_id": name if kind == "metric" else None,
                "unit": "money" if kind == "metric" else None}

    series = {"columns": [col("month"), col("net_sales", "metric")],
              "rows": [["2026-01", "1.00"], ["2026-02", "2.00"], ["2026-03", "3.00"]]}
    assert _spark(series, 1) == {"metric_id": "net_sales", "unit": "money",
                                 "points": ["1.00", "2.00", "3.00"]}
    mixed = {"columns": [col("month"), col("currency"), col("net_sales", "metric")],
             "rows": [["2026-01", "UZS", "1"], ["2026-01", "USD", "1"], ["2026-02", "UZS", "2"]]}
    assert _spark(mixed, 2) is None  # valyutalar aralash — chizilmaydi
    branches = {"columns": [col("branch"), col("net_sales", "metric")], "rows": [["A", "1"]] * 3}
    assert _spark(branches, 1) is None  # vaqt qatori emas
    short = {"columns": series["columns"], "rows": series["rows"][:2]}
    assert _spark(short, 1) is None
