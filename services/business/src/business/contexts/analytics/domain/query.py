"""Semantik so‘rov (QuerySpec) va uning invariantlari. LLM taklif qiladi, bu yer tekshiradi."""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from business.kernel.errors import ValidationFailed

from .metrics import (
    CATALOG,
    CRM_COMPONENTS,
    RECEIVABLE_COMPONENTS,
    Dimension,
    MetricDefinition,
)

MAX_METRICS = 6
MAX_DIMENSIONS = 2
MAX_PERIOD = timedelta(days=366 * 5)
DEFAULT_LIMIT = 500
MAX_LIMIT = 5000
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class InvalidQuery(ValidationFailed):
    code = "INVALID_QUERY"


class UnknownMetric(InvalidQuery):
    code = "UNKNOWN_METRIC"


class UnsupportedDimension(InvalidQuery):
    code = "UNSUPPORTED_DIMENSION"


@dataclass(frozen=True, slots=True)
class Period:
    start: date
    end: date  # ikkala chegara ham kiradi

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise InvalidQuery("Davr boshi oxiridan keyin bo‘lishi mumkin emas.")
        if self.end - self.start > MAX_PERIOD:
            raise InvalidQuery("Davr 5 yildan oshmasligi kerak.")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def is_incomplete(self, today: date) -> bool:
        """Joriy tugallanmagan davr (MTD) — to‘liq davr bilan izohsiz solishtirilmaydi."""
        return self.end >= today


@dataclass(frozen=True, slots=True)
class Filters:
    branch_codes: tuple[str, ...] | None = None
    product_codes: tuple[str, ...] | None = None
    customer_codes: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class OrderBy:
    """Natija metrika qiymati bo‘yicha saralanadi (“top 10”); aks holda kesim kodi tartibida."""

    metric_id: str
    descending: bool = True


@dataclass(frozen=True, slots=True)
class QuerySpec:
    metric_ids: tuple[str, ...]
    period: Period
    dimensions: tuple[Dimension, ...] = ()
    filters: Filters = field(default_factory=Filters)
    currency: str | None = None
    limit: int = DEFAULT_LIMIT
    order_by: OrderBy | None = None

    def __post_init__(self) -> None:
        if self.order_by is not None and self.order_by.metric_id not in self.metric_ids:
            raise InvalidQuery("Saralash metrikasi so‘rovdagi metrikalardan biri bo‘lsin.")
        if not 1 <= len(self.metric_ids) <= MAX_METRICS:
            raise InvalidQuery(f"1–{MAX_METRICS} ta metrika tanlang.")
        if len(set(self.metric_ids)) != len(self.metric_ids):
            raise InvalidQuery("Metrikalar takrorlanmasin.")
        if len(self.dimensions) > MAX_DIMENSIONS or len(set(self.dimensions)) != len(
            self.dimensions
        ):
            raise InvalidQuery(f"Ko‘pi bilan {MAX_DIMENSIONS} ta turli o‘lcham.")
        if sum(1 for d in self.dimensions if d.is_time) > 1:
            raise InvalidQuery("Bitta vaqt o‘lchami tanlang (oy, hafta yoki kun).")
        if self.currency is not None and not _CURRENCY_RE.fullmatch(self.currency):
            raise InvalidQuery("Valyuta ISO 4217 kodi bo‘lishi kerak.")
        if not 1 <= self.limit <= MAX_LIMIT:
            raise InvalidQuery(f"limit 1–{MAX_LIMIT} oralig‘ida.")
        definitions = [self._definition(m) for m in self.metric_ids]
        kinds = {self._kind(d) for d in definitions}
        if len(kinds) > 1:
            raise InvalidQuery(
                "Savdo, debitorlik va CRM metrikalarini bitta so‘rovda aralashtirib bo‘lmaydi."
            )
        for d in definitions:
            for dim in self.dimensions:
                if dim not in d.dimensions:
                    raise UnsupportedDimension(
                        f"“{d.name}” metrikasi “{dim.value}” kesimida hisoblanmaydi."
                    )

    @property
    def kind(self) -> str:
        """Manba turi: `sales` (savdo/qaytarish), `receivable` (debitorlik), `crm` (bitimlar)."""
        return self._kind(CATALOG[self.metric_ids[0]])

    @property
    def is_receivable(self) -> bool:
        return self.kind == "receivable"

    @property
    def is_crm(self) -> bool:
        return self.kind == "crm"

    @property
    def definitions(self) -> list[MetricDefinition]:
        return [CATALOG[m] for m in self.metric_ids]

    @staticmethod
    def _definition(metric_id: str) -> MetricDefinition:
        try:
            return CATALOG[metric_id]
        except KeyError:
            raise UnknownMetric(f"Noma’lum metrika: {metric_id}") from None

    @staticmethod
    def _kind(d: MetricDefinition) -> str:
        if set(d.components) & RECEIVABLE_COMPONENTS:
            return "receivable"
        if set(d.components) & CRM_COMPONENTS:
            return "crm"
        return "sales"


def previous_period(period: Period) -> Period:
    """Xuddi shu uzunlikdagi oldingi davr (to‘liq oy bo‘lsa — oldingi to‘liq oy)."""
    if period.start.day == 1 and (period.end + timedelta(days=1)).day == 1:
        end = period.start - timedelta(days=1)
        return Period(end.replace(day=1), end)
    return Period(period.start - timedelta(days=period.days), period.start - timedelta(days=1))
