"""TZ 7.1 va 20-bo‘lim: A01, A02, A06, A07 domen darajasida."""

from datetime import date
from decimal import Decimal as D

import pytest

from business.contexts.analytics.domain.ingestion import Entity, screen
from business.contexts.analytics.domain.metrics import (
    CATALOG,
    Dimension,
    compute,
    contributions,
    growth,
)
from business.contexts.analytics.domain.metrics import (
    Component as C,
)
from business.contexts.analytics.domain.query import (
    InvalidQuery,
    Period,
    QuerySpec,
    UnknownMetric,
    UnsupportedDimension,
    previous_period,
)

A01 = {C.ORDER_NET: D("950"), C.DISCOUNTS: D("50"), C.RETURNS_NET: D("100"),
       C.ORDER_COST: D("500"), C.RETURN_COST: D("0"), C.COST_MISSING_ROWS: D("0")}


def test_a01_net_sales_profit_margin() -> None:
    # 1000 savdo − 50 chegirma = 950 (ORDER_NET), − 100 qaytarish.
    assert compute("net_sales", A01).value == D("850")
    assert compute("gross_profit", A01).value == D("350")
    assert compute("gross_margin", A01).value == D("41.18")
    assert compute("discounts", A01).value == D("50")


def test_margin_is_null_when_net_sales_zero() -> None:
    v = compute("gross_margin", {C.ORDER_NET: D("0")})
    assert v.value is None and v.note


def test_missing_cost_is_disclosed() -> None:
    v = compute("gross_profit", {**A01, C.COST_MISSING_ROWS: D("3")})
    assert v.note and "3 ta" in v.note


def test_a02_growth_from_zero_is_absolute_only() -> None:
    change = growth(D("100"), D("0"))
    assert change.pct is None and change.absolute == D("100") and change.note


def test_a07_growth_from_negative_is_absolute_only() -> None:
    change = growth(D("-50"), D("-100"))
    assert change.pct is None and change.absolute == D("50")


def test_growth_percent_rounding() -> None:
    assert growth(D("110"), D("90")).pct == D("22.22")
    assert growth(D("80"), D("100")).pct == D("-20.00")


def test_a06_contributions_explain_total_change() -> None:
    total, items = contributions({"TOS": D("500"), "SAM": D("200")},
                                 {"TOS": D("519"), "SAM": D("281")})
    assert total == D("-100")
    assert items[0].member == "SAM" and items[0].share_of_change_pct == D("81.00")
    assert sum(i.change for i in items) == total


def test_contributions_with_zero_total_have_no_share() -> None:
    total, items = contributions({"A": D("10"), "B": D("0")}, {"A": D("0"), "B": D("10")})
    assert total == 0 and all(i.share_of_change_pct is None for i in items)


def period(a: str, b: str) -> Period:
    return Period(date.fromisoformat(a), date.fromisoformat(b))


def test_query_spec_validation() -> None:
    QuerySpec(("net_sales", "gross_margin"), period("2026-08-01", "2026-08-31"),
              (Dimension.BRANCH, Dimension.MONTH))
    with pytest.raises(UnknownMetric):
        QuerySpec(("net_profit",), period("2026-08-01", "2026-08-31"))
    with pytest.raises(UnsupportedDimension):
        QuerySpec(("receivables_open",), period("2026-08-01", "2026-08-31"), (Dimension.MONTH,))
    with pytest.raises(InvalidQuery):
        QuerySpec(("net_sales", "receivables_open"), period("2026-08-01", "2026-08-31"))
    with pytest.raises(InvalidQuery):
        QuerySpec(("net_sales",), period("2026-08-01", "2026-08-31"),
                  (Dimension.MONTH, Dimension.DAY))
    with pytest.raises(InvalidQuery):
        period("2026-09-01", "2026-08-01")


def test_previous_period() -> None:
    assert previous_period(period("2026-08-01", "2026-08-31")) == period("2026-07-01", "2026-07-31")
    assert previous_period(period("2026-03-01", "2026-03-31")) == period("2026-02-01", "2026-02-28")
    assert previous_period(period("2026-08-10", "2026-08-19")) == period("2026-07-31", "2026-08-09")
    assert period("2026-09-01", "2026-09-30").is_incomplete(date(2026, 9, 27))


def test_catalog_units_and_dimensions() -> None:
    assert CATALOG["gross_margin"].unit == "percent"
    assert Dimension.MONTH not in CATALOG["receivables_open"].dimensions


def line(source_id: str, qty: str = "1", **kw: str) -> dict[str, str]:
    return {"source_id": source_id, "quantity": qty, "gross_amount": "10", "discount_amount": "0",
            **kw}


def test_screen_quarantines_all_duplicate_copies_and_bad_quantities() -> None:
    result = screen(Entity.SALES_ORDER_LINE,
                    [line("A"), line("B"), line("B", gross_amount="12"), line("C", qty="0")])
    assert [r["source_id"] for r in result.accepted] == ["A"]
    reasons = {q.record["source_id"]: q.reason for q in result.quarantined}
    assert set(reasons) == {"B", "C"} and len(result.quarantined) == 3
    assert "takrorlangan" in reasons["B"]
