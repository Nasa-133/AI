from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.budget import BudgetLimits, BudgetUsage


class SqlBudgetStore:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._c = conn
        self._t = tenant_id

    async def lock(self) -> None:
        await self._c.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                              {"k": f"budget:{self._t}"})

    async def limits(self) -> BudgetLimits | None:
        r = (await self._c.execute(text(
            "SELECT daily_limit, monthly_limit, currency FROM governance.budgets"))).first()
        return None if r is None else BudgetLimits(r.daily_limit, r.monthly_limit,
                                                   r.currency.strip())

    async def set_limits(self, limits: BudgetLimits, *, user_id: UUID) -> None:
        await self._c.execute(text(
            "INSERT INTO governance.budgets (tenant_id, currency, daily_limit, monthly_limit,"
            " updated_by, updated_at) VALUES (:t, :c, :d, :m, :u, now())"
            " ON CONFLICT (tenant_id) DO UPDATE SET daily_limit = :d, monthly_limit = :m,"
            " updated_by = :u, updated_at = now()"),
            {"t": self._t, "c": limits.currency, "d": limits.daily, "m": limits.monthly,
             "u": user_id})

    async def usage(self, timezone: str) -> BudgetUsage:
        # Davr chegarasi korxona vaqt mintaqasida; ochiq rezerv + yakuniy sarf.
        r = (await self._c.execute(text(
            "SELECT coalesce(sum(CASE WHEN (created_at AT TIME ZONE :tz)::date ="
            "   (now() AT TIME ZONE :tz)::date THEN amount END), 0) AS day,"
            " coalesce(sum(CASE WHEN date_trunc('month', created_at AT TIME ZONE :tz) ="
            "   date_trunc('month', now() AT TIME ZONE :tz) THEN amount END), 0) AS month"
            " FROM (SELECT created_at, CASE status WHEN 'reserved' THEN reserved"
            "   WHEN 'settled' THEN actual ELSE 0 END AS amount FROM governance.budget_usage"
            "   WHERE created_at > now() - interval '32 days') u"), {"tz": timezone})).one()
        return BudgetUsage(Decimal(r.day), Decimal(r.month))

    async def reserve(self, task_id: UUID, reservation_id: UUID, amount: Decimal) -> bool:
        r = await self._c.execute(text(
            "INSERT INTO governance.budget_usage (tenant_id, task_id, reservation_id, reserved,"
            " status, created_at) VALUES (:t, :task, :rid, :a, 'reserved', now())"
            " ON CONFLICT DO NOTHING RETURNING task_id"),
            {"t": self._t, "task": task_id, "rid": reservation_id, "a": amount})
        return r.first() is not None

    async def settle(self, task_id: UUID, actual: Decimal, input_tokens: int,
                     output_tokens: int) -> None:
        await self._c.execute(text(
            "UPDATE governance.budget_usage SET status = 'settled', actual = :a,"
            " input_tokens = :i, output_tokens = :o, settled_at = now()"
            " WHERE task_id = :task AND status = 'reserved'"),
            {"a": actual, "i": input_tokens, "o": output_tokens, "task": task_id})

    async def release(self, task_id: UUID) -> None:
        await self._c.execute(text(
            "UPDATE governance.budget_usage SET status = 'released', settled_at = now()"
            " WHERE task_id = :task AND status = 'reserved'"), {"task": task_id})
