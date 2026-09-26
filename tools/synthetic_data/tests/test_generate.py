"""Sintetik ma’lumot generatori testlari.

`recompute` generator kodidan foydalanmaydi: CSV’larni hujjatlashtirilgan qoidalar bo‘yicha
qaytadan hisoblaydi. Shu tariqa expected.json, fayllar va README’dagi qoidalar mosligi
tekshiriladi — ingestion ham aynan shu qoidalarga amal qilishi kerak.
"""

import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pytest

TOOL_DIR = Path(__file__).resolve().parents[1]
REPO = TOOL_DIR.parents[1]
FIXTURES = REPO / "fixtures" / "synthetic"
sys.path.insert(0, str(TOOL_DIR))

import generate  # noqa: E402

TASHKENT = timezone(timedelta(hours=5))
CSV_FILES = ["sotuvlar.csv", "qaytarishlar.csv", "ombor_harakatlari.csv", "debitorlik.csv"]
DEMO_SEED, DEMO_ROWS = 42, 19_000


# ------------------------------------------------------------------ helpers

def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_expected(directory: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
    return data


def checksums(directory: Path) -> dict[str, str]:
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in [*CSV_FILES, "expected.json"]}


def parse_local(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment.astimezone(TASHKENT) if moment.tzinfo else None


def pct(profit: Decimal, net: Decimal) -> str | None:
    if net == 0:
        return None
    return str((profit / net * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def recompute(directory: Path) -> dict[str, Any]:
    as_of = date.fromisoformat(load_expected(directory)["as_of"])
    sales = read(directory / "sotuvlar.csv")

    id_counts = Counter(row["Hujjat ID"] for row in sales)
    quarantine: dict[str, set[str]] = {"duplicate_conflict": set(), "invalid_date": set(),
                                       "non_positive_quantity": set()}
    for row in sales:
        if id_counts[row["Hujjat ID"]] > 1:
            quarantine["duplicate_conflict"].add(row["Hujjat ID"])
        elif parse_local(row["Sana"]) is None:
            quarantine["invalid_date"].add(row["Hujjat ID"])
        elif Decimal(row["Miqdor"]) <= 0:
            quarantine["non_positive_quantity"].add(row["Hujjat ID"])
    excluded = set().union(*quarantine.values())

    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}

    def bucket(row: dict[str, str]) -> dict[str, Any]:
        moment = parse_local(row["Sana"])
        assert moment is not None
        key = (row["Valyuta"], f"{moment.year}-{moment.month:02d}", row["Filial kodi"])
        return buckets.setdefault(key, {"gross": Decimal(0), "disc": Decimal(0),
                                        "ret": Decimal(0), "cogs": Decimal(0), "missing": 0})

    for row in sales:
        if row["Hujjat ID"] in excluded or row["Holat"] != "tasdiqlangan":
            continue
        b = bucket(row)
        b["gross"] += Decimal(row["Summa"])
        b["disc"] += Decimal(row["Chegirma"])
        if row["Tannarx"]:
            b["cogs"] += Decimal(row["Tannarx"])
        else:
            b["missing"] += 1
    for row in read(directory / "qaytarishlar.csv"):
        if row["Holat"] != "tasdiqlangan":
            continue
        b = bucket(row)
        b["ret"] += Decimal(row["Summa"])
        b["cogs"] -= Decimal(row["Tannarx"])

    def summary(b: dict[str, Any]) -> dict[str, Any]:
        net = b["gross"] - b["disc"] - b["ret"]
        profit = net - b["cogs"]
        return {"net_sales": str(net), "gross_profit": str(profit),
                "cogs_missing_rows": b["missing"], "gross_margin_pct": pct(profit, net)}

    result_sales: dict[tuple[str, str, str], dict[str, Any]] = {
        key: summary(b) for key, b in buckets.items()}

    receivables: dict[str, dict[str, Any]] = {}
    for row in read(directory / "debitorlik.csv"):
        acc = receivables.setdefault(row["Valyuta"], {"outstanding": Decimal(0),
                                                      "overdue": Decimal(0), "docs": 0})
        open_amount = Decimal(row["Summa"]) - Decimal(row["To‘langan"])
        acc["outstanding"] += open_amount
        if date.fromisoformat(row["To‘lov muddati"]) < as_of and open_amount > 0:
            acc["overdue"] += open_amount
            acc["docs"] += 1

    movements = sorted(read(directory / "ombor_harakatlari.csv"),
                       key=lambda r: (r["Sana"], r["Harakat ID"]))
    balances: Counter[str] = Counter()
    running: Counter[tuple[str, str]] = Counter()
    negative_products: set[str] = set()
    last_sale: dict[str, date] = {}
    for row in movements:
        qty = int(row["Miqdor"])
        balances[row["Mahsulot kodi"]] += qty
        running[(row["Ombor kodi"], row["Mahsulot kodi"])] += qty
        if running[(row["Ombor kodi"], row["Mahsulot kodi"])] < 0:
            negative_products.add(row["Mahsulot kodi"])
        if row["Turi"] == "sotuv":
            moment = parse_local(row["Sana"])
            assert moment is not None
            day = moment.date()
            last_sale[row["Mahsulot kodi"]] = max(day, last_sale.get(row["Mahsulot kodi"], day))

    return {
        "quarantine": quarantine,
        "sales": result_sales,
        "receivables": receivables,
        "balances": balances,
        "negative_products": negative_products,
        "last_sale": last_sale,
        "as_of": as_of,
    }


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope="module", params=["golden", "demo"])
def dataset(request: pytest.FixtureRequest) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    directory = FIXTURES / request.param
    return directory, load_expected(directory), recompute(directory)


# -------------------------------------------------------- expected == recompute

def test_sales_aggregates_match_recomputation(dataset: tuple[Path, dict, dict]) -> None:
    _, expected, actual = dataset
    flattened = {
        (currency, month, branch): values
        for currency, months in expected["sales"].items()
        for month, entry in months.items()
        for branch, values in entry["branches"].items()
    }
    assert set(flattened) == set(actual["sales"])
    for key, values in flattened.items():
        subset = {k: values[k] for k in actual["sales"][key]}
        assert subset == actual["sales"][key], key


def test_month_totals_are_sum_of_branches(dataset: tuple[Path, dict, dict]) -> None:
    _, expected, _ = dataset
    for months in expected["sales"].values():
        for entry in months.values():
            for field in ("gross_sales", "discounts", "returns", "net_sales", "cogs",
                          "gross_profit"):
                total = sum(Decimal(b[field]) for b in entry["branches"].values())
                assert Decimal(entry["total"][field]) == total


def test_receivables_match(dataset: tuple[Path, dict, dict]) -> None:
    _, expected, actual = dataset
    assert set(expected["receivables"]) == set(actual["receivables"])
    for currency, acc in actual["receivables"].items():
        got = expected["receivables"][currency]
        assert Decimal(got["outstanding"]) == acc["outstanding"]
        assert Decimal(got["overdue"]) == acc["overdue"]
        assert got["overdue_documents"] == acc["docs"]


def test_inventory_matches(dataset: tuple[Path, dict, dict]) -> None:
    _, expected, actual = dataset
    inventory = expected["inventory"]
    for product, balance in inventory["balance_by_product"].items():
        assert int(balance) == actual["balances"][product]
    slow = [p for p in inventory["balance_by_product"]
            if p not in actual["last_sale"]
            or (actual["as_of"] - actual["last_sale"][p]).days >= 60]
    assert inventory["slow_moving_products"] == slow


def test_quarantine_matches_rules(dataset: tuple[Path, dict, dict]) -> None:
    _, expected, actual = dataset
    listed = expected["scenarios"]["quarantine_expected"]["sotuvlar.csv"]
    assert {k: set(v) for k, v in listed.items()} == actual["quarantine"]


def test_row_counts_and_money_format(dataset: tuple[Path, dict, dict]) -> None:
    directory, expected, _ = dataset
    for name in CSV_FILES:
        rows = read(directory / name)
        assert expected["row_counts"][name] == len(rows)
        for row in rows:
            for column in ("Narx", "Summa", "Chegirma", "QQS", "Tannarx", "To‘langan",
                           "Birlik tannarxi"):
                value = row.get(column)
                if value:
                    assert value.split(".")[-1].isdigit() and len(value.split(".")[1]) == 2


# ------------------------------------------------------------------ golden

def test_golden_a01_exact_numbers() -> None:
    entry = load_expected(FIXTURES / "golden")["sales"]["UZS"]["2026-01"]["branches"]["TOS"]
    assert entry == {
        "gross_sales": "1000.00", "discounts": "50.00", "returns": "100.00",
        "net_sales": "850.00", "cogs": "500.00", "cogs_missing_rows": 0,
        "gross_profit": "350.00", "gross_margin_pct": "41.18",
    }


def test_golden_a02_branch_without_previous_month() -> None:
    sales = load_expected(FIXTURES / "golden")["sales"]["UZS"]
    assert "NAM" not in sales["2026-01"]["branches"]
    assert sales["2026-02"]["branches"]["NAM"]["net_sales"] == "100.00"


def test_golden_a07_negative_profit_both_months() -> None:
    sales = load_expected(FIXTURES / "golden")["sales"]["UZS"]
    assert sales["2026-03"]["branches"]["BUX"]["gross_profit"] == "-100.00"
    assert sales["2026-04"]["branches"]["BUX"]["gross_profit"] == "-50.00"


def test_golden_receivables_and_stock() -> None:
    expected = load_expected(FIXTURES / "golden")
    assert expected["receivables"]["UZS"] == {
        "outstanding": "450.40", "overdue": "338.40", "overdue_documents": 1}
    assert expected["inventory"]["balance_by_product"] == {"P001": "26", "P002": "6"}


# ------------------------------------------------------------------ demo scenarios

@pytest.fixture(scope="module")
def demo() -> dict[str, Any]:
    return load_expected(FIXTURES / "demo")


def test_demo_size_and_period(demo: dict[str, Any]) -> None:
    assert demo["seed"] == DEMO_SEED and demo["row_counts"]["sotuvlar.csv"] == DEMO_ROWS
    assert len(demo["sales"]["UZS"]) == 12
    total = sum(p.stat().st_size for p in FIXTURES.rglob("*") if p.is_file())
    assert total < 5_000_000


def test_demo_branch_opened_mid_period(demo: dict[str, Any]) -> None:
    s = demo["scenarios"]["branch_opened"]
    months = demo["sales"][s["currency"]]
    assert s["branch"] not in months[s["previous_month"]]["branches"]
    assert Decimal(months[s["first_month"]]["branches"][s["branch"]]["net_sales"]) > 0


def test_demo_profit_drop_is_explained_by_one_branch(demo: dict[str, Any]) -> None:
    s = demo["scenarios"]["profit_drop"]
    months = demo["sales"][s["currency"]]
    cur, prev = months[s["month"]], months[s["previous_month"]]
    total_delta = Decimal(cur["total"]["gross_profit"]) - Decimal(prev["total"]["gross_profit"])
    branch_delta = (Decimal(cur["branches"][s["driver_branch"]]["gross_profit"])
                    - Decimal(prev["branches"][s["driver_branch"]]["gross_profit"]))
    assert total_delta < 0
    assert branch_delta / total_delta > Decimal("0.5")


def test_demo_negative_gross_profit(demo: dict[str, Any]) -> None:
    s = demo["scenarios"]["negative_gross_profit"]
    assert Decimal(demo["sales"][s["currency"]][s["month"]]["branches"][s["branch"]]
                   ["gross_profit"]) < 0


def test_demo_has_small_usd_share_kept_separate(demo: dict[str, Any]) -> None:
    rows = demo["scenarios"]["currencies"]
    share = Decimal(rows["USD"]) / (rows["USD"] + rows["UZS"])
    assert Decimal("0.01") <= share <= Decimal("0.05")
    assert set(demo["sales"]) == {"UZS", "USD"}


def test_demo_missing_cost_share(demo: dict[str, Any]) -> None:
    m = demo["scenarios"]["missing_cost"]
    share = Decimal(m["rows_without_cost"]) / m["confirmed_rows"]
    assert Decimal("0.01") <= share <= Decimal("0.03")


def test_demo_quarantine_cases_present(demo: dict[str, Any]) -> None:
    q = demo["scenarios"]["quarantine_expected"]["sotuvlar.csv"]
    assert len(q["duplicate_conflict"]) >= 3
    assert len(q["invalid_date"]) >= 2 and len(q["non_positive_quantity"]) >= 2


def test_demo_inventory_scenarios() -> None:
    expected = load_expected(FIXTURES / "demo")
    actual = recompute(FIXTURES / "demo")
    slow = expected["inventory"]["slow_moving_products"]
    assert len(slow) >= 10
    assert set(expected["scenarios"]["slow_moving_designed"]) <= set(slow)
    assert actual["negative_products"] == {expected["scenarios"]["negative_stock"]["product"]}
    assert expected["scenarios"]["overdue_receivables_documents"] > 0


# ------------------------------------------------------------------ determinism

def test_same_seed_gives_identical_files(tmp_path: Path) -> None:
    generate.DemoGenerator(7, 1_500).run(tmp_path / "a")
    generate.DemoGenerator(7, 1_500).run(tmp_path / "b")
    generate.DemoGenerator(8, 1_500).run(tmp_path / "c")
    assert checksums(tmp_path / "a") == checksums(tmp_path / "b")
    assert checksums(tmp_path / "a")["sotuvlar.csv"] != checksums(tmp_path / "c")["sotuvlar.csv"]


def test_committed_fixtures_are_up_to_date(tmp_path: Path) -> None:
    generate.DemoGenerator(DEMO_SEED, DEMO_ROWS).run(tmp_path / "demo")
    generate.generate_golden(tmp_path / "golden")
    assert checksums(tmp_path / "demo") == checksums(FIXTURES / "demo")
    assert checksums(tmp_path / "golden") == checksums(FIXTURES / "golden")
