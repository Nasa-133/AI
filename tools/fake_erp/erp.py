"""Soxta ERP ma’lumot modeli: demo tarixi + bugungacha “jonli” yangi hujjatlar.

Haqiqiy ERP’ga o‘xshash xatti-harakat:
- maydon nomlari ERP uslubida (inglizcha, snake_case), pul va miqdor — satr (float emas);
- yozuvlar `updated_at` bo‘yicha tartiblangan, yangilari faqat oxiriga qo‘shiladi;
- demo tarixi (2025-09-01 — 2026-08-31) tugagach, har kun uchun yangi savdolar deterministik
  generatsiya qilinadi (sana urug‘i bilan) va faqat vaqti kelganlari ko‘rinadi — ERP “ishlab
  turgan” kabi: bir necha daqiqadan keyin yangi hujjatlar paydo bo‘ladi.

Ma’lumot sintetik; haqiqiy korxona ma’lumoti emas.
"""

import csv
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

TASHKENT = timezone(timedelta(hours=5))
HISTORY_END = date(2026, 8, 31)
CENT = Decimal("0.01")

Record = dict[str, str | None]

SALES_STATE = {"tasdiqlangan": "posted", "qoralama": "draft", "bekor qilingan": "cancelled"}
MOVEMENT_KIND = {"kirim": "receipt", "sotuv": "sale", "qaytarish": "return",
                 "ko‘chirish_kirim": "transfer_in", "ko‘chirish_chiqim": "transfer_out",
                 "tuzatish": "adjustment"}
WEEKDAY_FACTOR = [10, 10, 10, 10, 10, 11, 6]  # Du..Ya

RESOURCES = ("sales-invoice-lines", "sales-returns", "stock-movements", "receivables")


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _none(v: str | None) -> str | None:
    return v if v not in (None, "") else None


def _stamp(d: date, hh: int, mm: int) -> str:
    return datetime.combine(d, time(hh, mm), TASHKENT).isoformat()


def _money(v: Decimal) -> str:
    return str(v.quantize(CENT, rounding=ROUND_HALF_UP))


@dataclass
class ErpData:
    """Barcha resurslar: tarix (bir marta yuklanadi) + kunlik reja (so‘ralganda quriladi)."""

    history: dict[str, list[Record]]
    seed: int = 20260901
    _plans: dict[date, dict[str, list[Record]]] = field(default_factory=dict)

    @classmethod
    def load(cls, demo_dir: Path, seed: int = 20260901) -> "ErpData":
        sales = [{
            "line_id": r["Hujjat ID"], "invoice_no": r["Hujjat №"], "posted_at": r["Sana"],
            "branch_code": r["Filial kodi"], "branch_name": r["Filial"],
            "item_code": r["Mahsulot kodi"], "item_name": r["Mahsulot"],
            "customer_code": _none(r["Mijoz kodi"]), "customer_name": _none(r["Mijoz"]),
            "qty": r["Miqdor"], "price": r["Narx"], "amount": r["Summa"],
            "discount": r["Chegirma"], "vat": r["QQS"], "cost": _none(r["Tannarx"]),
            "currency": r["Valyuta"], "state": SALES_STATE.get(r["Holat"], r["Holat"]),
            "updated_at": r["Sana"],
        } for r in _read(demo_dir / "sotuvlar.csv")]
        returns = [{
            "return_id": r["Qaytarish ID"], "invoice_line_id": _none(r["Asl hujjat ID"]),
            "posted_at": r["Sana"], "branch_code": r["Filial kodi"],
            "item_code": r["Mahsulot kodi"], "customer_code": _none(r["Mijoz kodi"]),
            "qty": r["Miqdor"], "amount": r["Summa"], "vat": r["QQS"],
            "cost": _none(r["Tannarx"]), "currency": r["Valyuta"],
            "state": SALES_STATE.get(r["Holat"], r["Holat"]), "updated_at": r["Sana"],
        } for r in _read(demo_dir / "qaytarishlar.csv")]
        movements = [{
            "movement_id": r["Harakat ID"], "moved_at": r["Sana"],
            "warehouse_code": r["Ombor kodi"], "branch_code": r["Filial kodi"],
            "item_code": r["Mahsulot kodi"], "qty": r["Miqdor"],
            "kind": MOVEMENT_KIND.get(r["Turi"], r["Turi"]),
            "unit_cost": _none(r["Birlik tannarxi"]), "currency": r["Valyuta"],
            "updated_at": r["Sana"],
        } for r in _read(demo_dir / "ombor_harakatlari.csv")]
        receivables = [{
            "doc_id": r["Hujjat ID"], "customer_code": r["Mijoz kodi"],
            "customer_name": _none(r["Mijoz"]), "invoice_no": _none(r["Hujjat №"]),
            "doc_date": r["Sana"], "due_date": r["To‘lov muddati"], "amount": r["Summa"],
            "paid": r["To‘langan"], "currency": r["Valyuta"], "branch_code": r["Filial kodi"],
            "updated_at": datetime.combine(date.fromisoformat(r["Sana"]), time(18),
                                           TASHKENT).isoformat(),
        } for r in _read(demo_dir / "debitorlik.csv")]
        return cls({"sales-invoice-lines": sales, "sales-returns": returns,
                    "stock-movements": movements, "receivables": receivables}, seed)

    # --- jonli qism ---------------------------------------------------------------------

    def _invoices(self) -> list[list[Record]]:
        """Tarixdagi tasdiqlangan hujjatlar (qatorlari bilan) — yangi kun uchun namuna."""
        if not hasattr(self, "_invoice_cache"):
            by_no: dict[str, list[Record]] = {}
            bad: set[str] = set()
            for r in self.history["sales-invoice-lines"]:
                if r["state"] == "posted" and r["currency"] == "UZS":
                    by_no.setdefault(str(r["invoice_no"]), []).append(r)
                    # Tarixdagi ataylab buzilgan satrlar (karantin sinovi) namuna bo‘lmasin.
                    if _moment(r["posted_at"]) is None or not _positive(r["qty"]):
                        bad.add(str(r["invoice_no"]))
            self._invoice_cache = [lines for no, lines in sorted(by_no.items()) if no not in bad]
        return self._invoice_cache

    def plan(self, day: date) -> dict[str, list[Record]]:
        """Bitta kunning hujjatlari (deterministik). Vaqti kelmaganlari keyin filtrlanadi."""
        if day in self._plans:
            return self._plans[day]
        rng = random.Random(self.seed * 1000 + day.toordinal())  # noqa: S311 — sintetik ma’lumot
        invoices = self._invoices()
        count = max(1, round(18 * WEEKDAY_FACTOR[day.weekday()] / 10 * rng.uniform(0.8, 1.2)))
        out: dict[str, list[Record]] = {k: [] for k in RESOURCES}
        tag = day.strftime("%y%m%d")
        minutes = sorted(rng.randint(9 * 60, 20 * 60 + 59) for _ in range(count))
        for n, minute in enumerate(minutes, start=1):
            template = rng.choice(invoices)
            posted = _stamp(day, minute // 60, minute % 60)
            invoice_no = f"SV-{tag}-{n:03d}"
            total = Decimal(0)
            for i, t in enumerate(template, start=1):
                line_id = f"S{tag}{n:03d}{i:02d}"
                out["sales-invoice-lines"].append({
                    **t, "line_id": line_id, "invoice_no": invoice_no, "posted_at": posted,
                    "updated_at": posted})
                total += Decimal(str(t["amount"])) - Decimal(str(t["discount"])) + Decimal(
                    str(t["vat"]))
                unit_cost = (_money(Decimal(str(t["cost"])) / Decimal(str(t["qty"])))
                             if t["cost"] else None)
                out["stock-movements"].append({
                    "movement_id": f"H{tag}{n:03d}{i:02d}", "moved_at": posted,
                    "warehouse_code": f"{t['branch_code']}-01", "branch_code": t["branch_code"],
                    "item_code": t["item_code"], "qty": f"-{t['qty']}", "kind": "sale",
                    "unit_cost": unit_cost, "currency": t["currency"], "updated_at": posted})
                # Taxminan 2% qatorlar qaytariladi (o‘sha kuni kechqurun).
                if rng.random() < 0.02:
                    back = _stamp(day, 20, 59)
                    out["sales-returns"].append({
                        "return_id": f"Q{tag}{n:03d}{i:02d}", "invoice_line_id": line_id,
                        "posted_at": back, "branch_code": t["branch_code"],
                        "item_code": t["item_code"], "customer_code": t["customer_code"],
                        "qty": "1", "amount": _money(Decimal(str(t["price"]))),
                        "vat": _money(Decimal(str(t["price"])) * Decimal("0.12")),
                        "cost": (_money(Decimal(str(t["cost"])) / Decimal(str(t["qty"])))
                                 if t["cost"] else None),
                        "currency": t["currency"], "state": "posted", "updated_at": back})
            # Mijozli hujjatlarning ~30% nasiyaga (debitorlik).
            customer = template[0]["customer_code"]
            if customer and rng.random() < 0.3:
                out["receivables"].append({
                    "doc_id": f"R{tag}{n:03d}", "customer_code": customer,
                    "customer_name": template[0]["customer_name"], "invoice_no": invoice_no,
                    "doc_date": day.isoformat(),
                    "due_date": (day + timedelta(days=45)).isoformat(),
                    "amount": _money(total), "paid": "0.00", "currency": "UZS",
                    "branch_code": template[0]["branch_code"], "updated_at": posted})
        for rows in out.values():
            rows.sort(key=lambda r: (str(r["updated_at"]), str(next(iter(r.values())))))
        self._plans[day] = out
        return out

    def records(self, resource: str, as_of: datetime) -> list[Record]:
        """`as_of` paytidagi holat: tarix + shu paytgacha “kiritilgan” yangi hujjatlar."""
        rows = list(self.history[resource])
        day = HISTORY_END + timedelta(days=1)
        stamp = as_of.astimezone(TASHKENT).isoformat()
        while day <= as_of.astimezone(TASHKENT).date():
            rows.extend(r for r in self.plan(day)[resource] if str(r["updated_at"]) <= stamp)
            day += timedelta(days=1)
        return rows


def _moment(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None  # tarixdagi ataylab buzilgan sana (karantin sinovi) — faqat to‘liq sinxronda


def _positive(value: str | None) -> bool:
    try:
        return Decimal(str(value)) > 0
    except ArithmeticError:
        return False


def filter_since(rows: list[Record], since: str | None) -> list[Record]:
    if not since:
        return rows
    moment = datetime.fromisoformat(since)
    return [r for r in rows if (m := _moment(r["updated_at"])) is not None and m > moment]


Clock = Callable[[], datetime]


def page(rows: list[Record], offset: int, limit: int) -> tuple[list[Record], int | None]:
    chunk = rows[offset:offset + limit]
    nxt = offset + len(chunk)
    return chunk, (nxt if nxt < len(rows) else None)


def stats(data: ErpData, as_of: datetime) -> dict[str, Any]:
    return {r: len(data.records(r, as_of)) for r in RESOURCES}
