"""Metrika lug‘ati va formulalari (TZ 7.1). Faqat Decimal; DB’dan olingan yig‘indilar ustida.

SQL faqat yig‘indilarni (komponentlarni) hisoblaydi; metrikaning ma’nosi shu yerda.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

ZERO = Decimal("0")
HUNDRED = Decimal("100")
PERCENT_QUANT = Decimal("0.01")


class Unit(StrEnum):
    MONEY = "money"
    PERCENT = "percent"
    COUNT = "count"
    QUANTITY = "quantity"


class Subject(StrEnum):
    SALES = "sales"
    FINANCE = "finance"
    INVENTORY = "inventory"


class Dimension(StrEnum):
    MONTH = "month"
    WEEK = "week"
    DAY = "day"
    BRANCH = "branch"
    PRODUCT = "product"
    CUSTOMER = "customer"
    CURRENCY = "currency"

    @property
    def is_time(self) -> bool:
        return self in (Dimension.MONTH, Dimension.WEEK, Dimension.DAY)


DIMENSION_NAMES = {
    Dimension.MONTH: "Oy",
    Dimension.WEEK: "Hafta",
    Dimension.DAY: "Kun",
    Dimension.BRANCH: "Filial",
    Dimension.PRODUCT: "Mahsulot",
    Dimension.CUSTOMER: "Mijoz",
    Dimension.CURRENCY: "Valyuta",
}

SALES_DIMENSIONS = tuple(Dimension)
RECEIVABLE_DIMENSIONS = (Dimension.BRANCH, Dimension.CUSTOMER, Dimension.CURRENCY)


class Component(StrEnum):
    """SQL qaytaradigan yig‘indilar. Barchasi tasdiqlangan (`confirmed`) satrlar bo‘yicha."""

    ORDER_NET = "order_net"  # QQSsiz, chegirma bir marta ayrilgan
    DISCOUNTS = "discounts"
    RETURNS_NET = "returns_net"
    ORDER_COST = "order_cost"  # tannarxi bor satrlar
    RETURN_COST = "return_cost"
    COST_MISSING_ROWS = "cost_missing_rows"
    ORDER_COUNT = "order_count"
    QUANTITY = "quantity"
    RECEIVABLE_OPEN = "receivable_open"
    RECEIVABLE_OVERDUE = "receivable_overdue"


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    id: str
    name: str
    description: str
    unit: Unit
    subject: Subject
    version: int
    dimensions: tuple[Dimension, ...]
    components: tuple[Component, ...]


SALES_COMPONENTS = (Component.ORDER_NET, Component.RETURNS_NET)
PROFIT_COMPONENTS = (*SALES_COMPONENTS, Component.ORDER_COST, Component.RETURN_COST,
                     Component.COST_MISSING_ROWS)

CATALOG: dict[str, MetricDefinition] = {
    m.id: m
    for m in [
        MetricDefinition(
            "net_sales", "Sof savdo tushumi",
            "Tasdiqlangan savdo − qaytarish − chegirma, QQSsiz. Manbada ayrilgan chegirma qayta "
            "ayrilmaydi.",
            Unit.MONEY, Subject.SALES, 1, SALES_DIMENSIONS, SALES_COMPONENTS,
        ),
        MetricDefinition(
            "discounts", "Chegirmalar", "Tasdiqlangan savdodagi chegirmalar yig‘indisi.",
            Unit.MONEY, Subject.SALES, 1, SALES_DIMENSIONS, (Component.DISCOUNTS,),
        ),
        MetricDefinition(
            "returns", "Qaytarishlar", "Tasdiqlangan qaytarishlar, QQSsiz.",
            Unit.MONEY, Subject.SALES, 1, SALES_DIMENSIONS, (Component.RETURNS_NET,),
        ),
        MetricDefinition(
            "cogs", "Sotilgan mahsulot tannarxi",
            "Savdo tannarxi − qaytarilgan tannarx. Tannarxi yo‘q satrlar alohida ko‘rsatiladi.",
            Unit.MONEY, Subject.FINANCE, 1, SALES_DIMENSIONS,
            (Component.ORDER_COST, Component.RETURN_COST, Component.COST_MISSING_ROWS),
        ),
        MetricDefinition(
            "gross_profit", "Yalpi foyda", "Sof savdo tushumi − sotilgan mahsulot tannarxi.",
            Unit.MONEY, Subject.FINANCE, 1, SALES_DIMENSIONS, PROFIT_COMPONENTS,
        ),
        MetricDefinition(
            "gross_margin", "Yalpi marja", "Yalpi foyda / sof savdo tushumi × 100.",
            Unit.PERCENT, Subject.FINANCE, 1, SALES_DIMENSIONS, PROFIT_COMPONENTS,
        ),
        MetricDefinition(
            "order_count", "Hujjatlar soni", "Tasdiqlangan savdo hujjatlari soni.",
            Unit.COUNT, Subject.SALES, 1, SALES_DIMENSIONS, (Component.ORDER_COUNT,),
        ),
        MetricDefinition(
            "quantity_sold", "Sotilgan miqdor", "Tasdiqlangan savdo miqdori.",
            Unit.QUANTITY, Subject.SALES, 1, SALES_DIMENSIONS, (Component.QUANTITY,),
        ),
        MetricDefinition(
            "receivables_open", "Debitorlik qoldig‘i",
            "Davr oxiridagi to‘lanmagan qoldiq (summa − to‘langan).",
            Unit.MONEY, Subject.FINANCE, 1, RECEIVABLE_DIMENSIONS, (Component.RECEIVABLE_OPEN,),
        ),
        MetricDefinition(
            "receivables_overdue", "Muddati o‘tgan debitorlik",
            "Davr oxirida to‘lov muddati o‘tgan to‘lanmagan qoldiq.",
            Unit.MONEY, Subject.FINANCE, 1, RECEIVABLE_DIMENSIONS,
            (Component.RECEIVABLE_OVERDUE,),
        ),
    ]
}

RECEIVABLE_COMPONENTS = frozenset({Component.RECEIVABLE_OPEN, Component.RECEIVABLE_OVERDUE})


@dataclass(frozen=True, slots=True)
class MetricValue:
    value: Decimal | None
    note: str | None = None


def compute(metric_id: str, c: Mapping[Component, Decimal]) -> MetricValue:
    """Komponentlardan metrika qiymati. Maxraj 0 bo‘lsa `None` va izoh (TZ 7.1)."""

    def get(k: Component) -> Decimal:
        return c.get(k, ZERO)

    net_sales = get(Component.ORDER_NET) - get(Component.RETURNS_NET)
    cogs = get(Component.ORDER_COST) - get(Component.RETURN_COST)
    missing = int(get(Component.COST_MISSING_ROWS))
    missing_note = (
        f"{missing} ta savdo satrida tannarx yo‘q — foyda yuqoriroq ko‘rinishi mumkin"
        if missing else None
    )
    match metric_id:
        case "net_sales":
            return MetricValue(net_sales)
        case "discounts":
            return MetricValue(get(Component.DISCOUNTS))
        case "returns":
            return MetricValue(get(Component.RETURNS_NET))
        case "cogs":
            return MetricValue(cogs, missing_note)
        case "gross_profit":
            return MetricValue(net_sales - cogs, missing_note)
        case "gross_margin":
            if net_sales == ZERO:
                return MetricValue(None, "Sof savdo 0 — marja aniqlanmagan")
            return MetricValue(percent((net_sales - cogs) / net_sales * HUNDRED), missing_note)
        case "order_count":
            return MetricValue(get(Component.ORDER_COUNT))
        case "quantity_sold":
            return MetricValue(get(Component.QUANTITY))
        case "receivables_open":
            return MetricValue(get(Component.RECEIVABLE_OPEN))
        case "receivables_overdue":
            return MetricValue(get(Component.RECEIVABLE_OVERDUE))
    raise KeyError(metric_id)


def percent(value: Decimal) -> Decimal:
    return value.quantize(PERCENT_QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Change:
    absolute: Decimal
    pct: Decimal | None
    note: str | None


def growth(current: Decimal, previous: Decimal) -> Change:
    """(Joriy − oldingi) / oldingi × 100.

    Oldingi 0 yoki manfiy bo‘lsa foiz yo‘q (TZ 7.1, A02, A07).
    """
    absolute = current - previous
    if previous == ZERO:
        return Change(absolute, None, "Oldingi davr 0 — foiz o‘rniga mutlaq farq")
    if previous < ZERO:
        return Change(absolute, None,
                      "Oldingi qiymat manfiy — foiz yo‘nalishni noto‘g‘ri ko‘rsatadi, mutlaq farq")
    return Change(absolute, percent(absolute / previous * HUNDRED), None)


@dataclass(frozen=True, slots=True)
class Contribution:
    member: str
    current: Decimal
    previous: Decimal
    change: Decimal
    share_of_change_pct: Decimal | None


def contributions(
    current: Mapping[str, Decimal], previous: Mapping[str, Decimal]
) -> tuple[Decimal, list[Contribution]]:
    """Umumiy o‘zgarishga har a’zoning hisobiy hissasi (sababiy xulosa emas).

    Faqat additiv metrikalar uchun (marja kabi nisbatlar uchun emas).
    """
    members = sorted(set(current) | set(previous))
    total = sum((current.get(m, ZERO) - previous.get(m, ZERO) for m in members), ZERO)
    items = []
    for m in members:
        change = current.get(m, ZERO) - previous.get(m, ZERO)
        share = percent(change / total * HUNDRED) if total != ZERO else None
        items.append(Contribution(m, current.get(m, ZERO), previous.get(m, ZERO), change, share))
    # Umumiy o‘zgarish yo‘nalishiga eng ko‘p ta’sir qilganlar birinchi.
    items.sort(key=lambda x: (-(x.change * (1 if total >= ZERO else -1)), x.member))
    return total, items


ADDITIVE_METRICS = frozenset(
    m for m, d in CATALOG.items() if d.unit is not Unit.PERCENT
)
