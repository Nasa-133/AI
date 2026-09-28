"""Tahlil dashboardlari: OpenAI ulanguncha “analitik” vazifasi — faqat deterministik so‘rovlar.

Har widget Core’ning semantik so‘rovidan (QueryService) olinadi va saqlangan query_spec_id’ga
bog‘lanadi — agent yaratgan dashboard bilan bir xil: “Yangilash” bosilsa oxirgi snapshot bilan
qayta hisoblanadi. “Asosiy xulosalar” matni ham shu so‘rov natijalaridan hisoblanadi (raqam
taxmin qilinmaydi); sababiy xulosa emas — tekshirish uchun yo‘nalish.

setup_test_company.py --dashboards orqali chaqiriladi; alohida ham ishlaydi (tenant/user bilan).
"""

from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncEngine

from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.contexts.analytics.application.queries import QueryContext, QueryService
from business.contexts.dashboards.adapters.sql import AnalyticsQueryResults, SqlDashboardStore
from business.contexts.dashboards.application.service import DashboardService, Viewer
from business.platform.db import tenant_transaction

TZ = "Asia/Tashkent"
MONTHS = ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr",
          "oktabr", "noyabr", "dekabr"]


def month_end(d: date) -> date:
    return d.replace(day=monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    i = d.year * 12 + d.month - 1 + n
    return date(i // 12, i % 12 + 1, 1)


def label(d: date) -> str:
    return f"{d.year} {MONTHS[d.month]}"


def money(v: Any) -> str:
    x = Decimal(str(v))
    if abs(x) >= 10**9:
        return f"{x / 10**9:.2f} mlrd so‘m".replace(".", ",")
    if abs(x) >= 10**6:
        return f"{x / 10**6:.1f} mln so‘m".replace(".", ",")
    return f"{x:,.0f} so‘m".replace(",", " ")


def pct(v: Any) -> str:
    return f"{Decimal(str(v)):.1f}%".replace(".", ",")


class Builder:
    def __init__(self, conn: Any, tenant: UUID, user: UUID, today: date) -> None:
        self.q = QueryService(SqlAnalyticsStore(conn, tenant))
        self.ctx = QueryContext(user, None, today, TZ)
        self.dash = DashboardService(SqlDashboardStore(conn, tenant),
                                     AnalyticsQueryResults(SqlAnalyticsStore(conn, tenant)))
        self.user = user

    async def run(self, metrics: list[str], start: date, end: date, dims: list[str] | None = None,
                  *, order: str | None = None, asc: bool = False,
                  limit: int | None = None) -> dict[str, Any]:
        data, _ = await self.q.run(self.ctx, {
            "metric_ids": metrics, "date_range": {"from": start.isoformat(), "to": end.isoformat()},
            "dimensions": dims or [], "filters": {}, "currency": "UZS", "limit": limit,
            "order_by": {"metric_id": order, "direction": "asc" if asc else "desc"}
            if order else None})
        return data

    async def existing(self, title: str) -> UUID | None:
        cards = await self.dash.cards(Viewer(self.user, "owner"), limit=200, query=title)
        return next((UUID(c["id"]) for c in cards if c["title"] == title), None)

    async def create(self, title: str, description: str,
                     widgets: list[tuple[str, str, dict[str, Any] | str]]) -> None:
        """Bo‘lmasa yaratadi; bo‘lsa — yangi versiya (oxirgi ma’lumot va xulosalar bilan)."""
        spec = [{"title": t, "type": kind, "text": body if kind == "text" else None,
                 "query_spec_id": None if kind == "text" else body["query_spec_id"]}  # type: ignore[index]
                for t, kind, body in widgets]
        found = await self.existing(title)
        if found is None:
            await self.dash.create(user_id=self.user, task_id=None, title=title,
                                   description=description, widgets=spec)
            print(f"· dashboard: {title} ({len(widgets)} widget)", flush=True)
            return
        record = await self.dash.replace(Viewer(self.user, "owner"), found, title=title,
                                         description=description, widgets=spec)
        print(f"· dashboard yangilandi: {title} (v{record.version})", flush=True)


def col(data: dict[str, Any], metric: str) -> int:
    return next(i for i, c in enumerate(data["columns"]) if c.get("metric_id") == metric)


def rows_by(data: dict[str, Any], metric: str) -> dict[str, Decimal]:
    i = col(data, metric)
    return {str(r[0]): Decimal(r[i]) for r in data["rows"] if r[i] is not None}


async def insights(b: Builder, last: date, last3: date, year_start: date) -> str:
    """Raqamlar so‘rovlardan; har band tekshiriladigan fakt + tekshirish yo‘nalishi."""
    lm_start, lm_end = last.replace(day=1), month_end(last)
    prev = add_months(lm_start, -1)
    lines: list[str] = []

    monthly = await b.run(["net_sales", "gross_margin"], year_start, lm_end, ["month"])
    sales = rows_by(monthly, "net_sales")
    margin = rows_by(monthly, "gross_margin")
    cur, before = sales.get(lm_start.strftime("%Y-%m")), sales.get(prev.strftime("%Y-%m"))
    if cur is not None and before:
        change = (cur - before) / before * 100
        lines.append(f"- **Savdo:** {label(lm_start)} — {money(cur)} "
                     f"({'+' if change >= 0 else ''}{pct(change)} oldingi oyga nisbatan).")
    if margin:
        worst = min(margin, key=lambda k: margin[k])
        lines.append(f"- **Marja:** davr bo‘yicha eng past oy — {worst} ({pct(margin[worst])}); "
                     f"oxirgi oy {pct(margin.get(lm_start.strftime('%Y-%m'), 0))}.")

    by_branch_month = await b.run(["gross_margin"], year_start, lm_end, ["month", "branch"])
    drops = [(r[0], r[1], Decimal(r[-1])) for r in by_branch_month["rows"]
             if r[-1] is not None and Decimal(r[-1]) < 10]
    if drops:
        listed = "; ".join(f"{b_} — {m} ({pct(v)})" for m, b_, v in drops)
        lines.append(f"- **Marja keskin tushgan filial-oylar:** {listed}. Bu oylarda tannarx yoki "
                     "narx siyosatini (chegirmalar, zarar bilan sotuv) tekshirish kerak.")

    branches = await b.run(["net_sales", "gross_margin"], last3, lm_end, ["branch"])
    bm = rows_by(branches, "gross_margin")
    if bm:
        low = min(bm, key=lambda k: bm[k])
        others = [v for k, v in bm.items() if k != low]
        avg = sum(others, Decimal(0)) / len(others) if others else Decimal(0)
        lines.append(f"- **Filiallar ({label(last3)} — {label(lm_start)}):** eng past marja — "
                     f"{low} ({pct(bm[low])}), boshqalari o‘rtacha {pct(avg)}.")

    debt = await b.run(["receivables_open", "receivables_overdue"], lm_start, lm_end, ["branch"])
    opened, overdue = rows_by(debt, "receivables_open"), rows_by(debt, "receivables_overdue")
    total_open, total_over = sum(opened.values(), Decimal(0)), sum(overdue.values(), Decimal(0))
    if total_open:
        shares = {k: overdue.get(k, Decimal(0)) / v * 100 for k, v in opened.items() if v}
        top = max(shares, key=lambda k: shares[k])
        lines.append(f"- **Debitorlik ({lm_end.isoformat()}):** qoldiq {money(total_open)}, "
                     f"shundan muddati o‘tgan {money(total_over)} "
                     f"({pct(total_over / total_open * 100)}). Eng yuqori ulush — {top} "
                     f"({pct(shares[top])}).")

    crm = await b.run(["crm_win_rate"], year_start, lm_end, ["month"])
    wr = rows_by(crm, "crm_win_rate")
    if len(wr) >= 6:
        # Oxirgi 3 oy oldingi 3 oy bilan: ma’lumot boshidagi oylar qiyoslanmaydi — u yerda faqat
        # tez yopilgan bitimlar bor (keyin yutqaziladigan uzoq lidlar hali yopilmagan), konversiya
        # sun’iy yuqori ko‘rinadi.
        keys = sorted(wr)
        before_k, recent = keys[-6:-3], keys[-3:]
        a = sum((wr[k] for k in before_k), Decimal(0)) / 3
        z = sum((wr[k] for k in recent), Decimal(0)) / 3
        trend = ("deyarli o‘zgarmagan" if abs(z - a) < 2
                 else "pasaygan" if z < a else "oshgan")
        lines.append(f"- **CRM konversiyasi:** oxirgi 3 oy {pct(z)}, oldingi 3 oy {pct(a)} — "
                     f"{trend}.")
    crm_branch = await b.run(["crm_win_rate"], last3, lm_end, ["branch"], order="crm_win_rate",
                             asc=True)
    if crm_branch["rows"]:
        r = crm_branch["rows"][0]
        lines.append(f"- **Eng past konversiya ({label(last3)} — {label(lm_start)}):** {r[0]} "
                     f"({pct(r[-1])}). Shu filialda sotuv jarayoni va lidlar sifatini "
                     "ko‘rish kerak.")
    channels = await b.run(["crm_win_rate", "crm_deals_created"], add_months(lm_start, -11),
                           lm_end, ["channel"], order="crm_win_rate")
    if len(channels["rows"]) >= 2:
        best, worst_c = channels["rows"][0], channels["rows"][-1]
        lines.append(f"- **Kanallar (12 oy):** eng samarali — {best[0]} ({pct(best[1])}), "
                     f"eng past — {worst_c[0]} ({pct(worst_c[1])}).")
    pipe = await b.run(["crm_pipeline_open"], b.ctx.today.replace(day=1), b.ctx.today, ["stage"],
                       order="crm_pipeline_open")
    stages = rows_by(pipe, "crm_pipeline_open")
    if stages:
        total = sum(stages.values(), Decimal(0))
        biggest = max(stages, key=lambda k: stages[k])
        lines.append(f"- **Ochiq voronka:** {money(total)}; {pct(stages[biggest] / total * 100)} "
                     f"qismi “{biggest}” bosqichida — uzoq turib qolgan bitimlarni ko‘rib chiqing.")
    head = (f"Tahlil: {b.ctx.today.isoformat()} holatiga, faqat tasdiqlangan ma’lumot va "
            "deterministik so‘rovlar asosida. Bular faktlar va tekshirish yo‘nalishlari — sababni "
            "isbotlamaydi.")
    return head + "\n\n" + "\n".join(lines)


async def build_dashboards(engine: AsyncEngine, tenant: UUID, user: UUID) -> None:
    today = datetime.now(UTC).astimezone(ZoneInfo(TZ)).date()
    last = add_months(today.replace(day=1), -1)  # oxirgi to‘liq oy
    lm_start, lm_end = last, month_end(last)
    last3 = add_months(last, -2)
    year_start = add_months(last, -11)
    async with tenant_transaction(engine, tenant_id=tenant, user_id=user) as conn:
        b = Builder(conn, tenant, user, today)
        period = f"{label(year_start)} — {label(lm_start)}"

        await b.create("Rahbar paneli",
                       f"Asosiy ko‘rsatkichlar, {label(lm_start)}; trend: {period}.", [
            ("Asosiy xulosalar", "text", await insights(b, last, last3, year_start)),
            (f"Sof savdo — {label(lm_start)}", "kpi", await b.run(["net_sales"], lm_start, lm_end)),
            (f"Yalpi marja — {label(lm_start)}", "kpi",
             await b.run(["gross_margin"], lm_start, lm_end)),
            (f"Yutilgan bitimlar summasi — {label(lm_start)}", "kpi",
             await b.run(["crm_won_amount"], lm_start, lm_end)),
            (f"Konversiya — {label(lm_start)}", "kpi",
             await b.run(["crm_win_rate"], lm_start, lm_end)),
            ("Debitorlik qoldig‘i", "kpi", await b.run(["receivables_open"], lm_start, lm_end)),
            ("Muddati o‘tgan debitorlik", "kpi",
             await b.run(["receivables_overdue"], lm_start, lm_end)),
            ("Sof savdo va yalpi foyda — oylar", "line",
             await b.run(["net_sales", "gross_profit"], year_start, lm_end, ["month"])),
            ("Yalpi marja — oylar", "line",
             await b.run(["gross_margin"], year_start, lm_end, ["month"])),
        ])

        span3 = f"{label(last3)} — {label(lm_start)}"
        await b.create("Savdo va foyda", f"Filiallar va mahsulotlar: {span3}; trend: {period}.", [
            ("Sof savdo — oylar", "line",
             await b.run(["net_sales"], year_start, lm_end, ["month"])),
            (f"Filiallar — {span3}", "table",
             await b.run(["net_sales", "gross_profit", "gross_margin", "returns"], last3, lm_end,
                         ["branch"], order="net_sales")),
            (f"Filiallar sof savdosi — {span3}", "bar",
             await b.run(["net_sales"], last3, lm_end, ["branch"], order="net_sales")),
            ("Filiallar marjasi — oylar bo‘yicha", "table",
             await b.run(["gross_margin"], add_months(last, -5), lm_end, ["month", "branch"])),
            (f"Top 15 mahsulot — {span3}", "table",
             await b.run(["net_sales", "gross_margin"], last3, lm_end, ["product"],
                         order="net_sales", limit=15)),
            (f"Eng past marjali 10 mahsulot — {span3}", "table",
             await b.run(["gross_margin", "net_sales"], last3, lm_end, ["product"],
                         order="gross_margin", asc=True, limit=10)),
            (f"Qaytarishlar — {span3}", "bar",
             await b.run(["returns"], last3, lm_end, ["branch"], order="returns")),
        ])

        await b.create("CRM — savdo voronkasi",
                       f"Bitimlar, konversiya va kanallar; trend: {period}.", [
            ("Ochiq voronka — bosqichlar (bugun)", "bar",
             await b.run(["crm_pipeline_open"], today.replace(day=1), today, ["stage"],
                         order="crm_pipeline_open")),
            ("Yangi va yutilgan bitimlar — oylar", "line",
             await b.run(["crm_deals_created", "crm_deals_won"], year_start, lm_end, ["month"])),
            ("Konversiya — oylar", "line",
             await b.run(["crm_win_rate"], year_start, lm_end, ["month"])),
            (f"Konversiya filiallar bo‘yicha — {span3}", "table",
             await b.run(["crm_win_rate", "crm_deals_won", "crm_won_amount"], last3, lm_end,
                         ["branch"], order="crm_win_rate", asc=True)),
            ("Kanallar samaradorligi — 12 oy", "table",
             await b.run(["crm_deals_created", "crm_deals_won", "crm_win_rate", "crm_avg_deal"],
                         add_months(lm_start, -11), lm_end, ["channel"], order="crm_win_rate")),
            (f"Yutilgan bitimlar summasi — {span3}", "bar",
             await b.run(["crm_won_amount"], last3, lm_end, ["branch"], order="crm_won_amount")),
        ])

        await b.create("Debitorlik",
                       f"{lm_end.isoformat()} holatiga qoldiq va muddati o‘tgan qarz.", [
            ("Jami qoldiq", "kpi", await b.run(["receivables_open"], lm_start, lm_end)),
            ("Muddati o‘tgan", "kpi", await b.run(["receivables_overdue"], lm_start, lm_end)),
            ("Filiallar: qoldiq va muddati o‘tgan", "bar",
             await b.run(["receivables_open", "receivables_overdue"], lm_start, lm_end, ["branch"],
                         order="receivables_overdue")),
            ("Muddati o‘tgan qarzi eng katta 15 mijoz", "table",
             await b.run(["receivables_overdue", "receivables_open"], lm_start, lm_end,
                         ["customer"], order="receivables_overdue", limit=15)),
        ])


__all__ = ["build_dashboards", "timedelta"]
