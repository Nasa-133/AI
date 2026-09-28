"""Soxta CRM: savdo voronkasi (bitimlar) — ERP mijozlari asosida, vaqt o‘tishi bilan jonli.

Har kun uchun yangi lidlar deterministik (sana urug‘i bilan) yaratiladi; har bitimning taqdiri
(yutiladi / yutqaziladi / hali ochiq) va yopilish muddati oldindan belgilanadi, lekin API faqat
`as_of` paytidagi holatni ko‘rsatadi: bitim bosqichma-bosqich o‘tadi va vaqti kelganda yopiladi.
Shuning uchun har sinxronda ochiq bitimlar kamayib, yopilganlari ko‘payadi — haqiqiy CRM kabi.

Tahlil uchun ssenariy: 2026-06 da Samarqand filialida konversiya keskin pasayadi.
Ma’lumot sintetik; haqiqiy korxona ma’lumoti emas.
"""

import csv
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

TASHKENT = timezone(timedelta(hours=5))
START = date(2025, 9, 1)
RESOURCES = ("deals",)
Record = dict[str, str | None]

OPEN_STAGES = ("Yangi lid", "Uchrashuv", "Taklif yuborildi", "Muzokara")
WON_STAGE, LOST_STAGE = "Yutildi", "Yutqazildi"
CHANNELS = (("Tavsiya", 30), ("Instagram", 25), ("Telegram", 20), ("Veb-sayt", 15),
            ("Ko‘rgazma", 10))
WEEKDAY_LEADS = [7, 7, 7, 7, 6, 4, 1]  # Du..Ya
WIN_RATE = 0.38
LOSS_RATE = 0.34  # qolgani — sust lidlar (uzoq ochiq, keyin yutqaziladi)
SCENARIO = {"branch": "SAM", "month": (2026, 6), "win_rate": 0.12}


@dataclass(frozen=True, slots=True)
class Customer:
    code: str
    name: str
    branch: str
    typical: Decimal  # odatiy hujjat summasi


@dataclass(frozen=True, slots=True)
class Deal:
    deal_id: str
    number: str
    customer: Customer
    amount: Decimal
    channel: str
    created: datetime
    outcome: str  # won | lost
    closes: datetime


def _money(v: Decimal) -> str:
    return str(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@dataclass
class CrmData:
    customers: list[Customer]
    seed: int = 20250901
    _days: dict[date, list[Deal]] = field(default_factory=dict)

    @classmethod
    def load(cls, demo_dir: Path, seed: int = 20250901) -> "CrmData":
        """Mijozlar va ularning odatiy xarid summasi ERP demo savdolaridan olinadi."""
        totals: dict[str, list[Decimal]] = {}
        info: dict[str, tuple[str, str]] = {}
        with (demo_dir / "sotuvlar.csv").open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                code = r["Mijoz kodi"]
                if not code or r["Holat"] != "tasdiqlangan" or r["Valyuta"] != "UZS":
                    continue
                try:
                    amount = Decimal(r["Summa"])
                except ArithmeticError:
                    continue
                totals.setdefault(code, []).append(amount)
                info[code] = (r["Mijoz"] or code, r["Filial kodi"])
        customers = [Customer(code, info[code][0], info[code][1],
                              sorted(v)[len(v) // 2] * 4)  # bitim — bir necha oylik xarid
                     for code, v in sorted(totals.items()) if len(v) >= 3]
        return cls(customers, seed)

    def day(self, d: date) -> list[Deal]:
        if d in self._days:
            return self._days[d]
        rng = random.Random(self.seed * 1000 + d.toordinal())  # noqa: S311 — sintetik ma’lumot
        count = max(0, round(WEEKDAY_LEADS[d.weekday()] * rng.uniform(0.7, 1.3)))
        minutes = sorted(rng.randint(9 * 60, 19 * 60) for _ in range(count))
        channels, weights = zip(*CHANNELS, strict=True)
        deals = []
        for n, minute in enumerate(minutes, start=1):
            c = rng.choice(self.customers)
            created = datetime.combine(d, time(minute // 60, minute % 60), TASHKENT)
            scenario = (c.branch == SCENARIO["branch"]
                        and (created.year, created.month) == SCENARIO["month"])
            win = float(SCENARIO["win_rate"]) if scenario else WIN_RATE
            roll = rng.random()
            if roll < win + LOSS_RATE:
                outcome = "won" if roll < win else "lost"
                closes = created + timedelta(days=rng.randint(3, 45), hours=rng.randint(0, 6))
            else:
                # Sust lid: uzoq ochiq turadi, 2–5 oydan keyin javobsiz deb yutqaziladi.
                outcome = "lost"
                closes = created + timedelta(days=rng.randint(60, 150))
            amount = (c.typical * Decimal(str(round(rng.uniform(0.6, 2.5), 2))))
            tag = d.strftime("%y%m%d")
            deals.append(Deal(f"D{tag}{n:02d}", f"BT-{tag}-{n:02d}", c, amount,
                              rng.choices(channels, weights)[0], created, outcome, closes))
        self._days[d] = deals
        return deals

    def records(self, resource: str, as_of: datetime) -> list[Record]:
        """`as_of` paytidagi CRM holati: yaratilgan bitimlar, har biri o‘z bosqichida."""
        if resource != "deals":
            return []
        now = as_of.astimezone(TASHKENT)
        out: list[Record] = []
        d = START
        while d <= now.date():
            for deal in self.day(d):
                if deal.created <= now:
                    out.append(_state(deal, now))
            d += timedelta(days=1)
        out.sort(key=lambda r: (str(r["updated_at"]), str(r["deal_id"])))
        return out


def _state(deal: Deal, now: datetime) -> Record:
    closed = deal.closes <= now
    if closed:
        stage, state, updated = (WON_STAGE if deal.outcome == "won" else LOST_STAGE,
                                 deal.outcome, deal.closes)
    else:
        # Ochiq bitim: yoshiga qarab bosqich (har ~5 kunda keyingisi, “Muzokara”da to‘xtaydi).
        age = (now - deal.created).days
        step = min(age // 5, len(OPEN_STAGES) - 1)
        stage, state = OPEN_STAGES[step], "open"
        updated = deal.created + timedelta(days=5 * step)
    return {
        "deal_id": deal.deal_id, "deal_no": deal.number,
        "client_code": deal.customer.code, "client_name": deal.customer.name,
        "branch": deal.customer.branch, "stage": stage, "state": state,
        "amount": _money(deal.amount), "currency": "UZS",
        "created_at": deal.created.isoformat(),
        "closed_at": deal.closes.isoformat() if closed else None,
        "lead_source": deal.channel, "updated_at": updated.isoformat(),
    }
