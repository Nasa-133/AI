from decimal import Decimal as D

from business.contexts.governance.domain.budget import (
    BudgetLimits,
    BudgetState,
    BudgetUsage,
    allows,
    status,
)


def test_status_thresholds() -> None:
    limits = BudgetLimits(daily=None, monthly=D("10"))
    assert status(limits, BudgetUsage(D("0"), D("7.99"))).state is BudgetState.OK
    assert status(limits, BudgetUsage(D("0"), D("8"))).state is BudgetState.WARNING  # 80%
    assert status(limits, BudgetUsage(D("0"), D("10"))).state is BudgetState.EXCEEDED


def test_daily_limit_counts_too() -> None:
    limits = BudgetLimits(daily=D("1"), monthly=D("100"))
    assert status(limits, BudgetUsage(D("0.9"), D("0.9"))).state is BudgetState.WARNING
    assert not allows(limits, BudgetUsage(D("0.96"), D("0.96")), D("0.05"))


def test_reservation_must_fit() -> None:
    limits = BudgetLimits(daily=None, monthly=D("1"))
    assert allows(limits, BudgetUsage(D("0"), D("0.95")), D("0.05"))
    assert not allows(limits, BudgetUsage(D("0"), D("0.96")), D("0.05"))
    assert allows(BudgetLimits(None, None), BudgetUsage(D("999"), D("999")), D("1"))  # cheksiz
    assert not allows(BudgetLimits(None, D("0")), BudgetUsage(D("0"), D("0")), D("0.01"))
