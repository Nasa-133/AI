"""FakeProvider: oylar oralig‘i, dashboard nomi, jadval sarlavhalari (UI tekshiruvidan)."""

from datetime import date

from ai_runtime.adapters.fake_provider import (
    Period,
    _table,
    build_plan,
    dashboard_title,
    resolve_period,
)

TODAY = date(2026, 9, 27)
CATALOG = {
    "today": "2026-09-27", "timezone": "Asia/Tashkent",
    "metrics": [
        {"id": "net_sales", "name": "Sof savdo tushumi", "dimensions": ["month", "branch"]},
        {"id": "receivables_open", "name": "Debitorlik qoldig‘i", "dimensions": ["branch"]},
    ],
}


def test_month_range_is_resolved() -> None:
    period, _ = resolve_period("2026 yil yanvardan aprelgacha oylar bo‘yicha savdo", TODAY)
    assert period == Period(date(2026, 1, 1), date(2026, 4, 30))
    period, _ = resolve_period("2025 noyabr–fevral savdosi", TODAY)
    assert period == Period(date(2025, 11, 1), date(2026, 2, 28))


def test_range_is_cut_at_today() -> None:
    period, notes = resolve_period("2026 avgustdan dekabrgacha", TODAY)
    assert period.end == TODAY and notes


def test_single_month_still_works() -> None:
    period, _ = resolve_period("2026 yanvar savdosi", TODAY)
    assert period == Period(date(2026, 1, 1), date(2026, 1, 31))


def test_dashboard_title_and_headers_use_names() -> None:
    plan = build_plan("oylar bo‘yicha savdoni dashboard qil", CATALOG)
    title = dashboard_title(plan, CATALOG, {"period": {"from": "2026-01-01", "to": "2026-04-30"}})
    assert title == "Sof savdo tushumi — oy kesimida, 2026-01-01 — 2026-04-30"
    table = _table([{"name": "month", "kind": "dimension", "metric_id": None},
                    {"name": "net_sales", "kind": "metric", "metric_id": "net_sales"}],
                   [["2026-01", "850.00"]], names={"net_sales": "Sof savdo tushumi"})
    assert table.startswith("| Oy | Sof savdo tushumi |")


def test_debt_maps_to_existing_core_metric() -> None:
    assert build_plan("mijozlar qarzi qancha", CATALOG).metric_ids == ["receivables_open"]
