"""AI budjeti qoidalari (TZ 19): 80% ogohlantirish, 100% da yangi pulli ish to‘xtaydi.

Boshlangan ishlar uchun rezerv: yangi vazifa (sarf + ochiq rezervlar + yangi rezerv) limitdan
oshsa yuborilmaydi. Limit berilmagan davr cheklanmaydi.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

WARNING_RATIO = Decimal("0.8")


class BudgetState(StrEnum):
    OK = "ok"
    WARNING = "warning"
    EXCEEDED = "exceeded"


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    daily: Decimal | None
    monthly: Decimal | None
    currency: str = "USD"


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    """Davr bo‘yicha: yakunlangan sarf + ochiq (hali yakunlanmagan) rezervlar."""

    day: Decimal
    month: Decimal


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    state: BudgetState
    ratio: Decimal  # eng yuqori foydalanish ulushi (0..)


def _ratio(spent: Decimal, limit: Decimal | None) -> Decimal:
    if limit is None:
        return Decimal("0")
    if limit == 0:
        return Decimal("1") if spent >= 0 else Decimal("0")
    return spent / limit


def status(limits: BudgetLimits, usage: BudgetUsage) -> BudgetStatus:
    ratio = max(_ratio(usage.day, limits.daily), _ratio(usage.month, limits.monthly))
    state = (BudgetState.EXCEEDED if ratio >= 1 else
             BudgetState.WARNING if ratio >= WARNING_RATIO else BudgetState.OK)
    return BudgetStatus(state, ratio)


def allows(limits: BudgetLimits, usage: BudgetUsage, reservation: Decimal) -> bool:
    """Yangi vazifa rezervi bilan ham limit ichida qoladimi."""
    for spent, limit in ((usage.day, limits.daily), (usage.month, limits.monthly)):
        if limit is not None and spent + reservation > limit:
            return False
    return True
