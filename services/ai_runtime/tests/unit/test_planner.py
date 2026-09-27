from datetime import date

import pytest

from ai_runtime.adapters.fake_provider import Period, build_plan, resolve_period
from tests.fake_core import default_data

TODAY = date(2026, 9, 27)
CATALOG = default_data()["list_available_metrics"]


@pytest.mark.parametrize(("text", "start", "end"), [
    ("O‘tgan oy filiallar savdosini solishtir", date(2026, 8, 1), date(2026, 8, 31)),
    ("o'tgan oy", date(2026, 8, 1), date(2026, 8, 31)),
    ("bu oy tushum", date(2026, 9, 1), date(2026, 9, 27)),
    ("2026 iyun savdosi", date(2026, 6, 1), date(2026, 6, 30)),
    ("iyun", date(2026, 6, 1), date(2026, 6, 30)),
    ("dekabr savdosi", date(2025, 12, 1), date(2025, 12, 31)),
    ("oxirgi 3 oy", date(2026, 6, 1), date(2026, 8, 31)),
    ("savdo qancha", date(2026, 8, 1), date(2026, 8, 31)),
])
def test_resolve_period(text: str, start: date, end: date) -> None:
    period, _ = resolve_period(text, TODAY)
    assert (period.start, period.end) == (start, end)


def test_incomplete_current_month_is_flagged() -> None:
    _, notes = resolve_period("bu oy", TODAY)
    assert notes and "to‘liq emas" in notes[0]


def test_previous_period() -> None:
    assert Period(date(2026, 3, 1), date(2026, 3, 31)).previous() == Period(
        date(2026, 2, 1), date(2026, 2, 28))
    assert Period(date(2026, 7, 1), date(2026, 9, 30)).previous() == Period(
        date(2026, 4, 1), date(2026, 6, 30))
    assert Period(date(2026, 9, 1), date(2026, 9, 27)).previous() == Period(
        date(2026, 8, 1), date(2026, 8, 27))
    assert Period(date(2026, 3, 1), date(2026, 3, 30)).previous() == Period(
        date(2026, 2, 1), date(2026, 2, 28))
    assert Period(date(2026, 8, 10), date(2026, 8, 19)).previous() == Period(
        date(2026, 7, 31), date(2026, 8, 9))


def test_plan_metric_dimension_and_intents() -> None:
    plan = build_plan("O‘tgan oy filiallar savdosini solishtir va dashboard qil", CATALOG)
    assert plan.metric_ids == ["net_sales"] and plan.dimensions == ["branch"]
    assert plan.compare and not plan.explain and plan.dashboard
    assert plan.currency == "UZS"


def test_why_question_triggers_explain() -> None:
    plan = build_plan("Bu oy foyda nega kamaydi?", CATALOG)
    assert plan.metric_ids == ["gross_profit"] and plan.explain and plan.compare
    assert any("yalpi foyda" in n for n in plan.notes)


def test_net_profit_is_not_invented() -> None:
    plan = build_plan("Sof foyda qancha?", CATALOG)
    assert plan.clarification and "Yalpi foyda" in plan.clarification


def test_unknown_metric_asks_one_question() -> None:
    plan = build_plan("Xodimlar kayfiyati qanday?", CATALOG)
    assert plan.clarification and plan.clarification.count("?") == 1
