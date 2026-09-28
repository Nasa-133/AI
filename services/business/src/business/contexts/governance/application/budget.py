"""Budjet: rezerv (vazifa AI’ga yuborilishidan oldin), yakuniy sarf, holat va limitlarni sozlash."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from business.kernel.errors import BusinessError

from ..domain.budget import BudgetLimits, allows, status
from ..ports.budget import BudgetStore

EXCEEDED_MESSAGE = ("AI budjeti limiti tugagan — yangi vazifa boshlanmadi. Korxona egasi "
                    "Sozlamalar → AI budjeti bo‘limida limitni oshirishi mumkin.")


class BudgetForbidden(BusinessError):
    code = "FORBIDDEN"


@dataclass(frozen=True, slots=True)
class Reservation:
    allowed: bool
    reservation_id: UUID | None
    message: str | None


def _fmt(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


class BudgetService:
    def __init__(self, store: BudgetStore, *, defaults: BudgetLimits, reservation: Decimal,
                 timezone: str) -> None:
        self._s = store
        self._defaults = defaults
        self._reservation = reservation
        self._tz = timezone

    async def _limits(self) -> BudgetLimits:
        return await self._s.limits() or self._defaults

    async def reserve(self, task_id: UUID) -> Reservation:
        await self._s.lock()
        limits = await self._limits()
        if not allows(limits, await self._s.usage(self._tz), self._reservation):
            return Reservation(False, None, EXCEEDED_MESSAGE)
        reservation_id = uuid4()
        await self._s.reserve(task_id, reservation_id, self._reservation)
        return Reservation(True, reservation_id, None)

    async def settle(self, task_id: UUID, usage: dict[str, Any], currency: str) -> None:
        cost = Decimal(str(usage.get("cost_estimate") or "0"))
        if currency != (await self._limits()).currency:
            cost = self._reservation  # boshqa valyuta: rezerv sarf deb olinadi (konservativ)
        await self._s.settle(task_id, max(cost, Decimal("0")), int(usage.get("input_tokens", 0)),
                             int(usage.get("output_tokens", 0)))

    async def release(self, task_id: UUID) -> None:
        await self._s.release(task_id)

    async def overview(self) -> dict[str, Any]:
        limits = await self._limits()
        usage = await self._s.usage(self._tz)
        st = status(limits, usage)
        return {"currency": limits.currency, "daily_limit": _fmt(limits.daily),
                "monthly_limit": _fmt(limits.monthly), "spent_today": _fmt(usage.day),
                "spent_month": _fmt(usage.month), "state": st.state.value,
                "percent": int(min(st.ratio, Decimal("9.99")) * 100),
                "reservation_per_task": _fmt(self._reservation)}

    async def update(self, role: str, user_id: UUID, daily: Decimal | None,
                     monthly: Decimal | None) -> dict[str, Any]:
        if role != "owner":
            raise BudgetForbidden("AI budjetini faqat korxona egasi o‘zgartiradi.")
        await self._s.set_limits(BudgetLimits(daily, monthly, self._defaults.currency),
                                 user_id=user_id)
        return await self.overview()
