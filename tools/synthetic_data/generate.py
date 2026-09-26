#!/usr/bin/env python3
"""AI Business Office uchun sintetik ERP eksporti generatori (faqat stdlib).

Ishlatish:
    python tools/synthetic_data/generate.py --seed 42 --rows 19000 --out fixtures/synthetic/demo
    python tools/synthetic_data/generate.py --golden --out fixtures/synthetic/golden

Chiqish fayllari vendor ERP eksportiga o‘xshaydi (o‘zbekcha ustun nomlari); canonical
nomlarga mapping keyinroq bajariladi. `expected.json` fayllarga yozilgan satrlarning
o‘zidan (string → Decimal) hisoblanadi, shuning uchun fayl va kutilgan natija ajralmaydi.

Hisoblash qoidalari (ingestion ham aynan shularga amal qilishi kerak):
- Faqat `Holat == "tasdiqlangan"` satrlar hisobga olinadi; qolganlari e’tiborsiz qoldiriladi
  (karantin emas).
- Karantin (sotuvlar.csv): (1) bir xil `Hujjat ID` bir necha marta kelsa — barcha nusxalari;
  (2) `Sana` offset bilan ISO 8601 sifatida o‘qilmasa; (3) `Miqdor` <= 0.
- Oy: `Sana` Asia/Tashkent (+05:00) mahalliy vaqtidagi oy. Qaytarish o‘z sanasi va filiali
  bo‘yicha hisoblanadi.
- Sof tushum = Summa − Chegirma − qaytarishlar Summa’si (hammasi QQSsiz).
- Tannarx: sotuv `Tannarx` yig‘indisi − qaytarish `Tannarx` yig‘indisi. Bo‘sh sotuv
  `Tannarx` 0 deb olinmaydi: summaga qo‘shilmaydi va `cogs_missing_rows`da sanaladi.
- Yalpi foyda = sof tushum − tannarx; marja % = foyda / sof tushum × 100,
  ROUND_HALF_UP 2 xona; sof tushum 0 bo‘lsa null.
- Debitorlik: qoldiq = Summa − To‘langan; `To‘lov muddati` < as_of va qoldiq > 0 bo‘lsa
  muddati o‘tgan.
- Ombor: qoldiq = barcha `Miqdor` yig‘indisi; sekin aylanadigan mahsulot — oxirgi `sotuv`
  harakatidan as_of gacha >= 60 kun o‘tgan yoki umuman sotilmagan.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, TextIO

GENERATOR_VERSION = "1.0.0"
TASHKENT = timezone(timedelta(hours=5))
START = date(2025, 9, 1)
AS_OF = date(2026, 8, 31)
SLOW_MOVING_DAYS = 60
STATUS_CONFIRMED = "tasdiqlangan"
CENT = Decimal("0.01")
ZERO = Decimal("0")
VAT_RATE = Decimal("0.12")
USD_RATE = Decimal("12650")

SALES_FILE = "sotuvlar.csv"
RETURNS_FILE = "qaytarishlar.csv"
MOVEMENTS_FILE = "ombor_harakatlari.csv"
RECEIVABLES_FILE = "debitorlik.csv"

FILES: dict[str, list[str]] = {
    SALES_FILE: [
        "Hujjat ID", "Hujjat №", "Sana", "Filial kodi", "Filial", "Mahsulot kodi", "Mahsulot",
        "Mijoz kodi", "Mijoz", "Miqdor", "Narx", "Summa", "Chegirma", "QQS", "Tannarx",
        "Valyuta", "Holat",
    ],
    RETURNS_FILE: [
        "Qaytarish ID", "Asl hujjat ID", "Sana", "Filial kodi", "Mahsulot kodi", "Mijoz kodi",
        "Miqdor", "Summa", "QQS", "Tannarx", "Valyuta", "Holat",
    ],
    MOVEMENTS_FILE: [
        "Harakat ID", "Sana", "Ombor kodi", "Filial kodi", "Mahsulot kodi", "Miqdor", "Turi",
        "Birlik tannarxi", "Valyuta",
    ],
    RECEIVABLES_FILE: [
        "Hujjat ID", "Mijoz kodi", "Mijoz", "Hujjat №", "Sana", "To‘lov muddati", "Summa",
        "To‘langan", "Valyuta", "Filial kodi",
    ],
}

QUARANTINE_REASONS = ("duplicate_conflict", "invalid_date", "non_positive_quantity")

BRANCHES: dict[str, str] = {
    "TOS": "Toshkent",
    "SAM": "Samarqand",
    "BUX": "Buxoro",
    "FAR": "Farg‘ona",
    "NAM": "Namangan",
}
BRANCH_WEIGHTS = {"TOS": 35, "SAM": 20, "BUX": 15, "FAR": 18, "NAM": 12}
BRANCH_OPENS = {"NAM": date(2026, 3, 1)}

# Oy bo‘yicha mavsumiylik (100 = oddiy oy). May va iyun teng: foyda pasayishi senariysi
# mavsumiylik bilan emas, SAM filiali bilan tushuntirilishi uchun.
MONTH_FACTOR = {9: 100, 10: 105, 11: 110, 12: 130, 1: 85, 2: 90, 3: 115, 4: 100, 5: 100,
                6: 100, 7: 90, 8: 95}
WEEKDAY_FACTOR = [10, 10, 10, 10, 10, 11, 6]  # Du..Ya

SCENARIO_BRANCH_OPENED = {"currency": "UZS", "branch": "NAM", "first_month": "2026-03",
                          "previous_month": "2026-02"}
SCENARIO_PROFIT_DROP = {"currency": "UZS", "month": "2026-06", "previous_month": "2026-05",
                        "driver_branch": "SAM"}
SCENARIO_NEGATIVE_GP = {"currency": "UZS", "month": "2026-04", "branch": "BUX"}
SLOW_MOVING_CUTOFF = date(2026, 5, 15)

BASE_PRODUCTS = [
    ("Un oliy nav", 9_000), ("Shakar", 14_000), ("Guruch lazer", 22_000),
    ("Paxta yog‘i", 24_000), ("Kungaboqar yog‘i", 26_000), ("Makaron", 12_000),
    ("Ko‘k choy", 35_000), ("Qora choy", 38_000), ("Tuz", 3_000), ("Grechka", 18_000),
    ("No‘xat", 20_000), ("Mosh", 21_000), ("Loviya", 23_000), ("Quruq sut", 60_000),
    ("Sariyog‘", 95_000), ("Pishloq", 85_000), ("Qahva", 120_000), ("Kakao", 70_000),
    ("Asal", 90_000), ("Murabbo", 30_000), ("Konserva no‘xat", 15_000),
    ("Tomat pastasi", 17_000), ("Sovun", 8_000), ("Kir kukuni", 45_000),
    ("Idish yuvish vositasi", 19_000), ("Shampun", 32_000), ("Tish pastasi", 16_000),
    ("Qog‘oz sochiq", 11_000), ("Suv 1.5 l", 4_000), ("Sharbat", 13_000),
]
PACKS = [("1 dona", 1, Decimal("1")), ("5 li", 5, Decimal("0.97")),
         ("10 li", 10, Decimal("0.95")), ("20 li", 20, Decimal("0.93")),
         ("50 li", 50, Decimal("0.90"))]

FIRST_NAMES = ["Aziz", "Jasur", "Dilshod", "Sardor", "Bekzod", "Otabek", "Sherzod", "Rustam",
               "Nodir", "Anvar", "Malika", "Dilnoza", "Gulnora", "Nigora", "Shahnoza",
               "Zarina", "Feruza", "Kamola", "Umid", "Javlon"]
LAST_NAMES = ["Aliyev", "Karimov", "Rahimov", "Toshmatov", "Yusupov", "Qodirov", "Nazarov",
              "Ergashev", "Saidov", "Xolmatov", "Mirzayev", "Sobirov", "Hamidov", "Rasulov",
              "Abdullayev"]
COMPANY_WORDS = ["Baraka", "Nur", "Oltin", "Ziyo", "Sharq", "Istiqbol", "Farovon", "Omad",
                 "Yulduz", "Diyor", "Mehr", "Zamin", "Bunyod", "Ravnaq", "Tong", "Sahovat"]
COMPANY_SUFFIXES = ["Savdo MChJ", "Market MChJ", "Trade MChJ", "Servis MChJ", "Invest MChJ"]


# --------------------------------------------------------------------------- helpers

def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value: Decimal) -> str:
    return str(money(value))


def stamp(day: date, hour: int, minute: int) -> str:
    return f"{day.isoformat()}T{hour:02d}:{minute:02d}:00+05:00"


def parse_stamp(value: str) -> datetime | None:
    """Offset’li ISO 8601 → Toshkent vaqti; o‘qib bo‘lmasa None (karantin sababi)."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(TASHKENT)


def month_of(moment: datetime) -> str:
    return f"{moment.year}-{moment.month:02d}"


def allocate(total: int, weights: list[int]) -> list[int]:
    """`total`ni butun sonli og‘irliklar bo‘yicha aniq taqsimlash (largest remainder)."""
    weight_sum = sum(weights)
    base = [total * w // weight_sum for w in weights]
    remainders = sorted(range(len(weights)),
                        key=lambda i: (-(total * weights[i] % weight_sum), i))
    for i in remainders[: total - sum(base)]:
        base[i] += 1
    return base


# ----------------------------------------------------------------------- expectations

def _new_bucket() -> dict[str, Any]:
    return {"gross_sales": ZERO, "discounts": ZERO, "returns": ZERO, "cogs": ZERO,
            "cogs_missing_rows": 0}


def finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    net = bucket["gross_sales"] - bucket["discounts"] - bucket["returns"]
    profit = net - bucket["cogs"]
    margin = None if net == 0 else fmt(profit / net * 100)
    return {
        "gross_sales": fmt(bucket["gross_sales"]),
        "discounts": fmt(bucket["discounts"]),
        "returns": fmt(bucket["returns"]),
        "net_sales": fmt(net),
        "cogs": fmt(bucket["cogs"]),
        "cogs_missing_rows": bucket["cogs_missing_rows"],
        "gross_profit": fmt(profit),
        "gross_margin_pct": margin,
    }


class Expectations:
    """Yozilgan satrlardan (string ko‘rinishida) kutilgan natijalarni yig‘adi."""

    def __init__(self, products: list[str]) -> None:
        self.products = products
        self.sales: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.receivables: dict[str, dict[str, Any]] = {}
        self.balances: dict[str, int] = {p: 0 for p in products}
        self.warehouse_stock: dict[tuple[str, str], int] = {}
        self.first_negative: dict[str, dict[str, str]] = {}
        self.last_sale: dict[str, date] = {}
        self.row_counts = {name: 0 for name in FILES}
        self.quarantine: dict[str, list[str]] = {reason: [] for reason in QUARANTINE_REASONS}
        self.confirmed_sales_rows = 0
        self.missing_cost_rows = 0
        self.currency_rows: dict[str, int] = {}

    def _bucket(self, currency: str, month: str, branch: str) -> dict[str, Any]:
        return self.sales.setdefault((currency, month, branch), _new_bucket())

    def sale(self, row: dict[str, str], quarantine: str | None) -> None:
        self.row_counts[SALES_FILE] += 1
        self.currency_rows[row["Valyuta"]] = self.currency_rows.get(row["Valyuta"], 0) + 1
        if quarantine is not None:
            ids = self.quarantine[quarantine]
            if row["Hujjat ID"] not in ids:
                ids.append(row["Hujjat ID"])
            return
        if row["Holat"] != STATUS_CONFIRMED:
            return
        moment = parse_stamp(row["Sana"])
        assert moment is not None, row
        bucket = self._bucket(row["Valyuta"], month_of(moment), row["Filial kodi"])
        bucket["gross_sales"] += Decimal(row["Summa"])
        bucket["discounts"] += Decimal(row["Chegirma"])
        self.confirmed_sales_rows += 1
        if row["Tannarx"] == "":
            bucket["cogs_missing_rows"] += 1
            self.missing_cost_rows += 1
        else:
            bucket["cogs"] += Decimal(row["Tannarx"])

    def sale_return(self, row: dict[str, str]) -> None:
        self.row_counts[RETURNS_FILE] += 1
        if row["Holat"] != STATUS_CONFIRMED:
            return
        moment = parse_stamp(row["Sana"])
        assert moment is not None, row
        bucket = self._bucket(row["Valyuta"], month_of(moment), row["Filial kodi"])
        bucket["returns"] += Decimal(row["Summa"])
        bucket["cogs"] -= Decimal(row["Tannarx"])

    def movement(self, row: dict[str, str]) -> None:
        self.row_counts[MOVEMENTS_FILE] += 1
        product, qty = row["Mahsulot kodi"], int(row["Miqdor"])
        self.balances[product] += qty
        key = (row["Ombor kodi"], product)
        stock = self.warehouse_stock.get(key, 0) + qty
        self.warehouse_stock[key] = stock
        if stock < 0 and product not in self.first_negative:
            self.first_negative[product] = {"warehouse": row["Ombor kodi"],
                                            "first_negative_at": row["Sana"]}
        if row["Turi"] == "sotuv":
            moment = parse_stamp(row["Sana"])
            assert moment is not None, row
            day = moment.date()
            if product not in self.last_sale or day > self.last_sale[product]:
                self.last_sale[product] = day

    def receivable(self, row: dict[str, str]) -> None:
        self.row_counts[RECEIVABLES_FILE] += 1
        acc = self.receivables.setdefault(
            row["Valyuta"], {"outstanding": ZERO, "overdue": ZERO, "overdue_documents": 0})
        open_amount = Decimal(row["Summa"]) - Decimal(row["To‘langan"])
        acc["outstanding"] += open_amount
        if date.fromisoformat(row["To‘lov muddati"]) < AS_OF and open_amount > 0:
            acc["overdue"] += open_amount
            acc["overdue_documents"] += 1

    def slow_moving(self) -> list[str]:
        return [p for p in self.products
                if p not in self.last_sale
                or (AS_OF - self.last_sale[p]).days >= SLOW_MOVING_DAYS]

    def result(self) -> dict[str, Any]:
        sales: dict[str, dict[str, Any]] = {}
        for currency, month, branch in sorted(self.sales):
            month_entry = sales.setdefault(currency, {}).setdefault(
                month, {"branches": {}, "total": _new_bucket()})
            bucket = self.sales[(currency, month, branch)]
            month_entry["branches"][branch] = finalize_bucket(bucket)
            total = month_entry["total"]
            for key in total:
                total[key] += bucket[key]
        for months in sales.values():
            for entry in months.values():
                entry["total"] = finalize_bucket(entry["total"])
        return {
            "sales": sales,
            "receivables": {
                currency: {"outstanding": fmt(v["outstanding"]), "overdue": fmt(v["overdue"]),
                           "overdue_documents": v["overdue_documents"]}
                for currency, v in sorted(self.receivables.items())
            },
            "inventory": {
                "slow_moving_threshold_days": SLOW_MOVING_DAYS,
                "balance_by_product": {p: str(self.balances[p]) for p in self.products},
                "slow_moving_products": self.slow_moving(),
            },
        }


# ---------------------------------------------------------------------------- writer

class DatasetWriter:
    """CSV fayllarga oqim bilan yozadi va har satrni Expectations’ga uzatadi."""

    def __init__(self, out: Path, products: list[str]) -> None:
        out.mkdir(parents=True, exist_ok=True)
        self.out = out
        self.expect = Expectations(products)
        self._handles: dict[str, TextIO] = {}
        self._writers: dict[str, csv.DictWriter[str]] = {}
        for name, columns in FILES.items():
            handle = (out / name).open("w", encoding="utf-8", newline="")
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            self._handles[name] = handle
            self._writers[name] = writer

    def sale(self, row: dict[str, str], quarantine: str | None = None) -> None:
        self._writers[SALES_FILE].writerow(row)
        self.expect.sale(row, quarantine)

    def sale_return(self, row: dict[str, str]) -> None:
        self._writers[RETURNS_FILE].writerow(row)
        self.expect.sale_return(row)

    def movement(self, row: dict[str, str]) -> None:
        self._writers[MOVEMENTS_FILE].writerow(row)
        self.expect.movement(row)

    def receivable(self, row: dict[str, str]) -> None:
        self._writers[RECEIVABLES_FILE].writerow(row)
        self.expect.receivable(row)

    def finish(self, header: dict[str, Any], scenarios: dict[str, Any]) -> dict[str, Any]:
        for handle in self._handles.values():
            handle.close()
        expected = {
            "generator_version": GENERATOR_VERSION,
            **header,
            "as_of": AS_OF.isoformat(),
            "timezone": "Asia/Tashkent",
            "row_counts": self.expect.row_counts,
            **self.expect.result(),
            "scenarios": {
                "quarantine_expected": {SALES_FILE: self.expect.quarantine},
                **scenarios,
            },
        }
        (self.out / "expected.json").write_text(
            json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return expected


# ---------------------------------------------------------------------- demo dataset

@dataclass(frozen=True)
class Product:
    code: str
    name: str
    base_price: Decimal
    pack_size: int
    cost_ratio: Decimal
    weight: int


@dataclass(frozen=True)
class Customer:
    code: str
    name: str
    branch: str
    currency: str
    late_payer: bool


@dataclass
class OpenLine:
    """Qaytarish uchun eslab qolingan sotuv satri."""

    line_id: str
    branch: str
    product: Product
    customer: Customer
    qty: int
    price: Decimal
    discount: Decimal
    currency: str


class DemoGenerator:
    ANOMALY_ROWS = 16  # 5 juft dublikat + 3 noto‘g‘ri sana + 3 manfiy miqdor

    def __init__(self, seed: int, rows: int) -> None:
        if rows < 500:
            raise ValueError("--rows kamida 500 bo‘lishi kerak")
        self.seed = seed
        self.rows = rows
        self.rng = random.Random(seed)
        scale = max(1, rows // 20_000)
        self.reorder_point = 300 * scale
        self.reorder_target = 1_000 * scale
        self.days = [START + timedelta(days=i) for i in range((AS_OF - START).days + 1)]
        self.products = self._make_products()
        self.slow_products = set(self.rng.sample([p.code for p in self.products], 12))
        candidates = [p.code for p in self.products if p.code not in self.slow_products]
        self.negative_product = self.rng.choice(candidates)
        self.customers = self._make_customers()
        self.seq = {"line": 0, "doc": 0, "return": 0, "move": 0, "recv": 0}
        self.stock: dict[tuple[str, str], int] = {}
        self.pending_returns: list[tuple[int, int, OpenLine, date]] = []
        self.pending_revisions: dict[int, list[dict[str, str]]] = {}

    # --- katalog -------------------------------------------------------------
    def _make_products(self) -> list[Product]:
        products = []
        for base_name, base_price in BASE_PRODUCTS:
            for pack_name, size, multiplier in PACKS:
                code = f"P{len(products) + 1:03d}"
                products.append(Product(
                    code=code,
                    name=f"{base_name} {pack_name}",
                    base_price=Decimal(base_price) * size * multiplier,
                    pack_size=size,
                    cost_ratio=Decimal(self.rng.randint(70, 85)) / 100,
                    weight=self.rng.randint(5, 20),
                ))
        return products

    def _make_customers(self) -> dict[str, list[Customer]]:
        by_branch: dict[str, list[Customer]] = {b: [] for b in BRANCHES}
        branch_codes = list(BRANCHES)
        weights = [BRANCH_WEIGHTS[b] for b in branch_codes]
        for i in range(800):
            branch = self.rng.choices(branch_codes, weights)[0]
            if self.rng.random() < 0.5:
                name = (f"{self.rng.choice(LAST_NAMES)} {self.rng.choice(FIRST_NAMES)} YaTT")
            else:
                name = f"{self.rng.choice(COMPANY_WORDS)} {self.rng.choice(COMPANY_SUFFIXES)}"
            by_branch[branch].append(Customer(
                code=f"M{i + 1:04d}", name=name, branch=branch, currency="UZS",
                late_payer=self.rng.random() < 0.10))
        usd = [Customer(code=f"M{801 + i:04d}", name=f"{w} Import MChJ", branch="TOS",
                        currency="USD", late_payer=False)
               for i, w in enumerate(COMPANY_WORDS[:8])]
        by_branch["USD"] = usd
        return by_branch

    # --- narxlar ---------------------------------------------------------------
    @staticmethod
    def _month_index(day: date) -> int:
        return (day.year - START.year) * 12 + day.month - START.month

    def price_uzs(self, product: Product, day: date) -> Decimal:
        inflated = product.base_price * (1 + Decimal(self._month_index(day)) * Decimal("0.008"))
        return money((inflated / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP) * 100)

    def price(self, product: Product, day: date, currency: str) -> Decimal:
        uzs = self.price_uzs(product, day)
        return uzs if currency == "UZS" else max(CENT, money(uzs / USD_RATE))

    def unit_cost(self, product: Product, day: date, currency: str = "UZS") -> Decimal:
        return money(self.price(product, day, currency) * product.cost_ratio)

    def discount_rate(self, branch: str, day: date) -> Decimal:
        month = (day.year, day.month)
        if branch == SCENARIO_NEGATIVE_GP["branch"] and month == (2026, 4):
            return Decimal(self.rng.randint(35, 45)) / 100  # likvidatsiya: zarar bilan sotuv
        if branch == SCENARIO_PROFIT_DROP["driver_branch"] and month == (2026, 6):
            return Decimal(self.rng.randint(28, 32)) / 100  # agressiv aksiya: marja ~0 dan past
        if self.rng.random() < 0.6:
            return ZERO
        return Decimal(self.rng.randint(1, 10)) / 100

    # --- asosiy sikl ---------------------------------------------------------
    def open_branches(self, day: date) -> list[str]:
        return [b for b in BRANCHES if day >= BRANCH_OPENS.get(b, START)]

    def run(self, out: Path) -> dict[str, Any]:
        writer = DatasetWriter(out, [p.code for p in self.products])
        weights = [MONTH_FACTOR[d.month] * WEEKDAY_FACTOR[d.weekday()] for d in self.days]
        counts = allocate(self.rows - self.ANOMALY_ROWS, weights)
        anomalies = self._anomaly_plan()
        for index, day in enumerate(self.days):
            sold_today: dict[tuple[str, str], int] = {}
            self._restock(writer, day)
            self._transfers(writer, day)
            self._sales(writer, day, counts[index], sold_today)
            for kind in anomalies.get(index, []):
                self._anomaly(writer, day, index, kind)
            for revision in self.pending_revisions.pop(index, []):
                writer.sale(revision, "duplicate_conflict")
            self._returns(writer, day)
            self._adjustments(writer, day, sold_today)
            self._sales_movements(writer, day, sold_today)

        negative = writer.expect.first_negative.get(self.negative_product)
        currencies = sorted(writer.expect.currency_rows)
        overdue_docs = sum(v["overdue_documents"] for v in writer.expect.receivables.values())
        return writer.finish(
            {"seed": self.seed, "rows_requested": self.rows,
             "period": {"from": START.isoformat(), "to": AS_OF.isoformat()}},
            {
                "branch_opened": SCENARIO_BRANCH_OPENED,
                "profit_drop": SCENARIO_PROFIT_DROP,
                "negative_gross_profit": SCENARIO_NEGATIVE_GP,
                "currencies": {c: writer.expect.currency_rows[c] for c in currencies},
                "missing_cost": {"confirmed_rows": writer.expect.confirmed_sales_rows,
                                 "rows_without_cost": writer.expect.missing_cost_rows},
                "slow_moving_designed": sorted(self.slow_products),
                "negative_stock": {"product": self.negative_product, **(negative or {})},
                "overdue_receivables_documents": overdue_docs,
            },
        )

    def _next(self, key: str) -> int:
        self.seq[key] += 1
        return self.seq[key]

    def _move(self, writer: DatasetWriter, day: date, hour: int, branch: str,
              product: Product, qty: int, kind: str) -> None:
        self.stock[(branch, product.code)] = self.stock.get((branch, product.code), 0) + qty
        writer.movement({
            "Harakat ID": f"H{self._next('move'):07d}",
            "Sana": stamp(day, hour, 0),
            "Ombor kodi": f"{branch}-01",
            "Filial kodi": branch,
            "Mahsulot kodi": product.code,
            "Miqdor": str(qty),
            "Turi": kind,
            "Birlik tannarxi": fmt(self.unit_cost(product, day)),
            "Valyuta": "UZS",
        })

    def _restock(self, writer: DatasetWriter, day: date) -> None:
        for branch in self.open_branches(day):
            for product in self.products:
                stock = self.stock.get((branch, product.code))
                if product.code == self.negative_product:
                    if stock is None:  # faqat boshlang‘ich kichik kirim, keyin to‘ldirilmaydi
                        self._move(writer, day, 8, branch, product, 40, "kirim")
                    continue
                if stock is None or stock < self.reorder_point:
                    self._move(writer, day, 8, branch, product,
                               self.reorder_target - (stock or 0), "kirim")

    def _transfers(self, writer: DatasetWriter, day: date) -> None:
        if day.day != 1 or day == START:
            return
        movable = [p for p in self.products
                   if p.code != self.negative_product and p.code not in self.slow_products]
        for product in self.rng.sample(movable, 3):
            targets = [b for b in self.open_branches(day) if b != "TOS"]
            target = self.rng.choice(targets)
            if self.stock.get(("TOS", product.code), 0) >= 2 * self.reorder_point:
                self._move(writer, day, 12, "TOS", product, -100, "ko‘chirish_chiqim")
                self._move(writer, day, 12, target, product, 100, "ko‘chirish_kirim")

    def _sales(self, writer: DatasetWriter, day: date, line_count: int,
               sold_today: dict[tuple[str, str], int]) -> None:
        branches = self.open_branches(day)
        branch_weights = [BRANCH_WEIGHTS[b] for b in branches]
        sellable = [p for p in self.products
                    if day < SLOW_MOVING_CUTOFF or p.code not in self.slow_products]
        product_weights = [p.weight for p in sellable]
        docs = []
        remaining = line_count
        while remaining > 0:
            size = min(remaining, self.rng.randint(1, 5))
            remaining -= size
            branch = self.rng.choices(branches, branch_weights)[0]
            if branch == "TOS" and self.rng.random() < 0.06:
                customer = self.rng.choice(self.customers["USD"])
            else:
                customer = self.rng.choice(self.customers[branch])
            roll = self.rng.random()
            status = (STATUS_CONFIRMED if roll < 0.94
                      else "qoralama" if roll < 0.97 else "bekor qilingan")
            chosen: list[Product] = []
            while len(chosen) < size:
                candidate = self.rng.choices(sellable, product_weights)[0]
                if candidate not in chosen:
                    chosen.append(candidate)
            hour, minute = self.rng.randint(9, 20), self.rng.randint(0, 59)
            docs.append((hour, minute, branch, customer, status, chosen))
        docs.sort(key=lambda doc: (doc[0], doc[1]))  # barqaror: bir vaqtdagilar tartibi saqlanadi
        for hour, minute, branch, customer, status, chosen in docs:
            self._document(writer, day, hour, minute, branch, customer, status, chosen,
                           sold_today)

    def _document(self, writer: DatasetWriter, day: date, hour: int, minute: int,
                  branch: str, customer: Customer, status: str, chosen: list[Product],
                  sold_today: dict[tuple[str, str], int]) -> None:
        doc_no = f"SV-{self._next('doc'):06d}"
        currency = customer.currency
        doc_total = ZERO
        for product in chosen:
            qty = self.rng.randint(1, max(2, 60 // product.pack_size))
            price = self.price(product, day, currency)
            gross = price * qty
            discount = money(gross * self.discount_rate(branch, day))
            vat = money((gross - discount) * VAT_RATE)
            has_cost = self.rng.random() >= 0.02
            line_id = f"S{self._next('line'):07d}"
            writer.sale({
                "Hujjat ID": line_id, "Hujjat №": doc_no, "Sana": stamp(day, hour, minute),
                "Filial kodi": branch, "Filial": BRANCHES[branch],
                "Mahsulot kodi": product.code, "Mahsulot": product.name,
                "Mijoz kodi": customer.code, "Mijoz": customer.name,
                "Miqdor": str(qty), "Narx": fmt(price), "Summa": fmt(gross),
                "Chegirma": fmt(discount), "QQS": fmt(vat),
                "Tannarx": fmt(self.unit_cost(product, day, currency) * qty) if has_cost else "",
                "Valyuta": currency, "Holat": status,
            })
            if status != STATUS_CONFIRMED:
                continue
            doc_total += gross - discount + vat
            key = (branch, product.code)
            sold_today[key] = sold_today.get(key, 0) + qty
            if self.rng.random() < 0.04:
                return_day = day + timedelta(days=self.rng.randint(1, 20))
                if return_day <= AS_OF:
                    line = OpenLine(line_id, branch, product, customer, qty, price, discount,
                                    currency)
                    heapq.heappush(self.pending_returns,
                                   (return_day.toordinal(), self.seq["line"], line, day))
        if status == STATUS_CONFIRMED and self.rng.random() < 0.35:
            self._receivable(writer, day, branch, customer, doc_no, doc_total)

    def _receivable(self, writer: DatasetWriter, day: date, branch: str, customer: Customer,
                    doc_no: str, total: Decimal) -> None:
        due = day + timedelta(days=self.rng.choice([15, 30, 45]))
        if customer.late_payer:
            paid = money(total * Decimal(self.rng.randint(0, 50)) / 100)
        elif due < AS_OF:
            paid = (total if self.rng.random() < 0.93
                    else money(total * Decimal(self.rng.randint(30, 90)) / 100))
        else:
            paid = money(total * Decimal(self.rng.choice([0, 0, 0, 25, 50])) / 100)
        writer.receivable({
            "Hujjat ID": f"R{self._next('recv'):06d}", "Mijoz kodi": customer.code,
            "Mijoz": customer.name, "Hujjat №": doc_no, "Sana": day.isoformat(),
            "To‘lov muddati": due.isoformat(), "Summa": fmt(total), "To‘langan": fmt(paid),
            "Valyuta": customer.currency, "Filial kodi": branch,
        })

    def _returns(self, writer: DatasetWriter, day: date) -> None:
        while self.pending_returns and self.pending_returns[0][0] == day.toordinal():
            _, _, line, sold_on = heapq.heappop(self.pending_returns)
            qty = self.rng.randint(1, line.qty)
            amount = money(line.price * qty - line.discount * qty / line.qty)
            status = STATUS_CONFIRMED if self.rng.random() < 0.95 else "qoralama"
            writer.sale_return({
                "Qaytarish ID": f"Q{self._next('return'):06d}",
                "Asl hujjat ID": line.line_id if self.rng.random() < 0.9 else "",
                "Sana": stamp(day, 18, self.rng.randint(0, 59)),
                "Filial kodi": line.branch, "Mahsulot kodi": line.product.code,
                "Mijoz kodi": line.customer.code, "Miqdor": str(qty), "Summa": fmt(amount),
                "QQS": fmt(amount * VAT_RATE),
                "Tannarx": fmt(self.unit_cost(line.product, sold_on, line.currency) * qty),
                "Valyuta": line.currency, "Holat": status,
            })
            if status == STATUS_CONFIRMED:
                self._move(writer, day, 18, line.branch, line.product, qty, "qaytarish")

    def _adjustments(self, writer: DatasetWriter, day: date,
                     sold_today: dict[tuple[str, str], int]) -> None:
        if day.day != 15:
            return
        for _ in range(3):
            branch = self.rng.choice(self.open_branches(day))
            product = self.rng.choice(self.products)
            delta = self.rng.choice([-3, -2, -1, 1, 2])
            key = (branch, product.code)
            if product.code == self.negative_product:
                continue
            if self.stock.get(key, 0) - sold_today.get(key, 0) + delta >= 0:
                self._move(writer, day, 21, branch, product, delta, "tuzatish")

    def _sales_movements(self, writer: DatasetWriter, day: date,
                         sold_today: dict[tuple[str, str], int]) -> None:
        by_code = {p.code: p for p in self.products}
        for (branch, code), qty in sold_today.items():
            self._move(writer, day, 23, branch, by_code[code], -qty, "sotuv")

    # --- karantin senariylari -------------------------------------------------
    def _anomaly_plan(self) -> dict[int, list[str]]:
        plan: dict[int, list[str]] = {}
        for index in (30, 90, 150, 210, 270):
            plan.setdefault(index, []).append("duplicate")
        for index in (60, 180, 300):
            plan.setdefault(index, []).append("invalid_date")
        for index in (45, 165, 285):
            plan.setdefault(index, []).append("negative_quantity")
        return plan

    def _anomaly(self, writer: DatasetWriter, day: date, index: int, kind: str) -> None:
        product = self.products[index % len(self.products)]
        customer = self.customers["TOS"][index % len(self.customers["TOS"])]
        qty = 3
        price = self.price(product, day, "UZS")
        gross = price * qty
        row = {
            "Hujjat ID": f"S{self._next('line'):07d}", "Hujjat №": f"SV-{self._next('doc'):06d}",
            "Sana": stamp(day, 21, 30), "Filial kodi": "TOS", "Filial": BRANCHES["TOS"],
            "Mahsulot kodi": product.code, "Mahsulot": product.name,
            "Mijoz kodi": customer.code, "Mijoz": customer.name, "Miqdor": str(qty),
            "Narx": fmt(price), "Summa": fmt(gross), "Chegirma": fmt(ZERO),
            "QQS": fmt(gross * VAT_RATE), "Tannarx": fmt(self.unit_cost(product, day) * qty),
            "Valyuta": "UZS", "Holat": STATUS_CONFIRMED,
        }
        if kind == "duplicate":
            writer.sale(row, "duplicate_conflict")
            revised_qty = qty + 1
            revision = {**row, "Miqdor": str(revised_qty), "Summa": fmt(price * revised_qty),
                        "QQS": fmt(price * revised_qty * VAT_RATE),
                        "Tannarx": fmt(self.unit_cost(product, day) * revised_qty)}
            self.pending_revisions.setdefault(index + 5, []).append(revision)
        elif kind == "invalid_date":
            bad = ["2026-02-30T10:15:00+05:00", "31.13.2026 10:00", "2026-13-01"][index % 3]
            writer.sale({**row, "Sana": bad}, "invalid_date")
        else:
            writer.sale({**row, "Miqdor": str(-qty), "Summa": fmt(-gross),
                         "QQS": fmt(-gross * VAT_RATE)}, "non_positive_quantity")


# -------------------------------------------------------------------- golden dataset

def generate_golden(out: Path) -> dict[str, Any]:
    """Qo‘lda tekshiriladigan kichik to‘plam: TZ A01, A02 va A07 holatlari."""
    writer = DatasetWriter(out, ["P001", "P002"])

    def sale(line_id: str, doc: str, when: str, branch: str, product: str, qty: int,
             price: str, discount: str, cost: str, status: str = STATUS_CONFIRMED) -> None:
        gross = Decimal(price) * qty
        writer.sale({
            "Hujjat ID": line_id, "Hujjat №": doc, "Sana": when, "Filial kodi": branch,
            "Filial": BRANCHES[branch], "Mahsulot kodi": product,
            "Mahsulot": {"P001": "Un oliy nav 1 dona", "P002": "Shakar 1 dona"}[product],
            "Mijoz kodi": "M0001", "Mijoz": "Baraka Savdo MChJ", "Miqdor": str(qty),
            "Narx": fmt(Decimal(price)), "Summa": fmt(gross), "Chegirma": discount,
            "QQS": fmt((gross - Decimal(discount)) * VAT_RATE), "Tannarx": cost,
            "Valyuta": "UZS", "Holat": status,
        })

    def move(move_id: str, when: str, branch: str, product: str, qty: int, kind: str) -> None:
        writer.movement({
            "Harakat ID": move_id, "Sana": when, "Ombor kodi": f"{branch}-01",
            "Filial kodi": branch, "Mahsulot kodi": product, "Miqdor": str(qty), "Turi": kind,
            "Birlik tannarxi": "50.00", "Valyuta": "UZS",
        })

    # A01: TOS, 2026-01 — yalpi 1000, chegirma 50, qaytarish 100, tannarx 500.
    sale("S0000001", "SV-000001", "2026-01-10T10:00:00+05:00", "TOS", "P001", 6, "100.00",
         "30.00", "300.00")
    sale("S0000002", "SV-000002", "2026-01-12T11:00:00+05:00", "TOS", "P002", 4, "100.00",
         "20.00", "200.00")
    # Tasdiqlanmagan satrlar hisobga olinmaydi.
    sale("S0000003", "SV-000003", "2026-01-15T12:00:00+05:00", "TOS", "P001", 1, "100.00",
         "0.00", "50.00", status="qoralama")
    sale("S0000004", "SV-000004", "2026-01-16T12:00:00+05:00", "TOS", "P001", 1, "100.00",
         "0.00", "50.00", status="bekor qilingan")
    # A02: NAM 2026-01 da savdo yo‘q, 2026-02 da sof tushum 100 → o‘sish foizi null.
    sale("S0000005", "SV-000005", "2026-02-05T10:00:00+05:00", "NAM", "P001", 1, "100.00",
         "0.00", "60.00")
    # A07: BUX yalpi foyda 2026-03 da −100, 2026-04 da −50.
    sale("S0000006", "SV-000006", "2026-03-05T10:00:00+05:00", "BUX", "P001", 4, "100.00",
         "0.00", "500.00")
    sale("S0000007", "SV-000007", "2026-04-05T10:00:00+05:00", "BUX", "P001", 9, "50.00",
         "0.00", "500.00")

    # Qaytarish tannarxi 0.00 (yaroqsiz tovar hisobdan chiqarilgan) — shuning uchun
    # A01 dagi sof tannarx sotuvdagi 500 ligicha qoladi.
    writer.sale_return({
        "Qaytarish ID": "Q000001", "Asl hujjat ID": "S0000001",
        "Sana": "2026-01-20T18:00:00+05:00", "Filial kodi": "TOS", "Mahsulot kodi": "P001",
        "Mijoz kodi": "M0001", "Miqdor": "1", "Summa": "100.00", "QQS": "12.00",
        "Tannarx": "0.00", "Valyuta": "UZS", "Holat": STATUS_CONFIRMED,
    })

    move("H0000001", "2026-01-01T08:00:00+05:00", "TOS", "P001", 20, "kirim")
    move("H0000002", "2026-01-01T08:00:00+05:00", "TOS", "P002", 10, "kirim")
    move("H0000003", "2026-01-10T23:00:00+05:00", "TOS", "P001", -6, "sotuv")
    move("H0000004", "2026-01-12T23:00:00+05:00", "TOS", "P002", -4, "sotuv")
    move("H0000005", "2026-01-20T18:00:00+05:00", "TOS", "P001", 1, "qaytarish")
    move("H0000006", "2026-02-01T08:00:00+05:00", "NAM", "P001", 5, "kirim")
    move("H0000007", "2026-02-05T23:00:00+05:00", "NAM", "P001", -1, "sotuv")
    move("H0000008", "2026-03-01T08:00:00+05:00", "BUX", "P001", 20, "kirim")
    move("H0000009", "2026-03-05T23:00:00+05:00", "BUX", "P001", -4, "sotuv")
    move("H0000010", "2026-04-05T23:00:00+05:00", "BUX", "P001", -9, "sotuv")

    writer.receivable({
        "Hujjat ID": "R000001", "Mijoz kodi": "M0001", "Mijoz": "Baraka Savdo MChJ",
        "Hujjat №": "SV-000001", "Sana": "2026-01-10", "To‘lov muddati": "2026-02-09",
        "Summa": "638.40", "To‘langan": "300.00", "Valyuta": "UZS", "Filial kodi": "TOS",
    })
    writer.receivable({
        "Hujjat ID": "R000002", "Mijoz kodi": "M0001", "Mijoz": "Baraka Savdo MChJ",
        "Hujjat №": "SV-000005", "Sana": "2026-02-05", "To‘lov muddati": "2026-09-30",
        "Summa": "112.00", "To‘langan": "0.00", "Valyuta": "UZS", "Filial kodi": "NAM",
    })

    return writer.finish(
        {"seed": None, "rows_requested": None,
         "period": {"from": "2026-01-01", "to": AS_OF.isoformat()}},
        {
            "a01": {"currency": "UZS", "month": "2026-01", "branch": "TOS"},
            "a02": {"currency": "UZS", "branch": "NAM", "month": "2026-02",
                    "previous_month": "2026-01"},
            "a07": {"currency": "UZS", "branch": "BUX", "month": "2026-04",
                    "previous_month": "2026-03"},
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rows", type=int, default=20_000, help="taxminiy sotuv satrlari soni")
    parser.add_argument("--golden", action="store_true",
                        help="kichik qo‘lda tekshiriladigan to‘plam")
    args = parser.parse_args()
    expected = generate_golden(args.out) if args.golden else DemoGenerator(
        args.seed, args.rows).run(args.out)
    print(json.dumps(expected["row_counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
