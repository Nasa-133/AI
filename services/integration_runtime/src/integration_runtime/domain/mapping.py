"""Manba → canonical mapping: tasdiqlash qoidalari va satrni normallashtirish.

Transformlar docs/design/stage1.md §4 jadvaliga aynan mos. Normallashtirib bo‘lmaydigan
satr `RowRejected` bilan rad etiladi (batch’ga kirmaydi, sababi hisobotda ko‘rinadi).
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from .canonical import ENTITY_FIELDS, FieldKind, FieldSpec

_DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

CanonicalValue = str | bool | None


class Transform(StrEnum):
    TEXT = "text"
    DECIMAL = "decimal"
    DECIMAL_OR_NULL = "decimal_or_null"
    DATETIME_TZ = "datetime_tz"
    DATE = "date"
    STATUS_MAP = "status_map"
    CONST = "const"


class RowRejected(Exception):
    """Satr canonical ko‘rinishga keltirilmadi. `reason` foydalanuvchiga ko‘rsatiladi."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MappingItem:
    canonical_field: str
    source_column: str | None
    transform: Transform
    constant: str | None = None


@dataclass(frozen=True, slots=True)
class SourceConfig:
    delimiter: str = ","
    encoding: str = "utf-8"
    status_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceMapping:
    entity: str
    items: tuple[MappingItem, ...]
    config: SourceConfig

    @property
    def source_columns(self) -> tuple[str, ...]:
        return tuple(i.source_column for i in self.items if i.source_column is not None)


_ALLOWED: dict[FieldKind, frozenset[Transform]] = {
    FieldKind.TEXT: frozenset({Transform.TEXT, Transform.CONST}),
    FieldKind.CURRENCY: frozenset({Transform.TEXT, Transform.CONST}),
    FieldKind.DECIMAL: frozenset({Transform.DECIMAL, Transform.DECIMAL_OR_NULL, Transform.CONST}),
    FieldKind.DATETIME: frozenset({Transform.DATETIME_TZ}),
    FieldKind.DATE: frozenset({Transform.DATE}),
    FieldKind.BOOL: frozenset({Transform.CONST}),
    FieldKind.ENUM: frozenset({Transform.STATUS_MAP, Transform.CONST}),
}


def _parse_const(spec: FieldSpec, constant: str | None) -> CanonicalValue:
    """`constant` — JSON qiymat matni (masalan `"false"`, `"\\"UZS\\""`)."""
    if constant is None:
        raise ValueError(f"{spec.name}: const uchun qiymat berilmagan")
    try:
        value: Any = json.loads(constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{spec.name}: const JSON emas: {constant!r}") from exc
    if value is None:
        if not spec.nullable:
            raise ValueError(f"{spec.name}: majburiy maydonga null const berilgan")
        return None
    if spec.kind is FieldKind.BOOL:
        if not isinstance(value, bool):
            raise ValueError(f"{spec.name}: const true/false bo‘lishi kerak")
        return value
    if not isinstance(value, str):
        raise ValueError(f"{spec.name}: const matn bo‘lishi kerak")
    _check_value(spec, value, error=ValueError)
    return value


def _check_value(spec: FieldSpec, value: str, *, error: type[Exception]) -> None:
    if spec.kind is FieldKind.DECIMAL and not _DECIMAL_RE.fullmatch(value):
        raise error(f"{spec.name}: son formati noto‘g‘ri: {value!r}")
    if spec.kind is FieldKind.CURRENCY and not _CURRENCY_RE.fullmatch(value):
        raise error(f"{spec.name}: valyuta ISO 4217 kodi emas: {value!r}")
    if spec.kind is FieldKind.ENUM and value not in spec.enum_values:
        raise error(f"{spec.name}: ruxsat etilmagan qiymat: {value!r}")
    if spec.kind in (FieldKind.TEXT, FieldKind.CURRENCY) and len(value) > spec.max_length:
        raise error(f"{spec.name}: {spec.max_length} belgidan uzun")


def validate_mapping(mapping: SourceMapping) -> list[str]:
    """Mapping xatolari ro‘yxati; bo‘sh ro‘yxat — mapping yaroqli."""
    fields = ENTITY_FIELDS.get(mapping.entity)
    if fields is None:
        return [f"Noma’lum entity: {mapping.entity}"]
    specs = {f.name: f for f in fields}
    errors: list[str] = []
    seen: set[str] = set()
    uses_status_map: list[FieldSpec] = []
    for item in mapping.items:
        spec = specs.get(item.canonical_field)
        if spec is None:
            errors.append(f"Noma’lum canonical maydon: {item.canonical_field}")
            continue
        if item.canonical_field in seen:
            errors.append(f"{item.canonical_field}: bir necha marta moslangan")
            continue
        seen.add(item.canonical_field)
        if item.transform not in _ALLOWED[spec.kind]:
            errors.append(f"{spec.name}: '{item.transform}' transformi {spec.kind} turiga mos emas")
            continue
        if item.transform is Transform.CONST:
            try:
                _parse_const(spec, item.constant)
            except ValueError as exc:
                errors.append(str(exc))
            continue
        if item.source_column is None and not spec.nullable:
            errors.append(f"{spec.name}: majburiy maydon uchun manba ustuni ko‘rsatilmagan")
        if item.transform is Transform.DECIMAL_OR_NULL and not spec.nullable:
            errors.append(f"{spec.name}: majburiy maydonda decimal_or_null ishlatib bo‘lmaydi")
        if item.transform is Transform.STATUS_MAP:
            uses_status_map.append(spec)
    for name, spec in specs.items():
        if name not in seen and not spec.nullable:
            errors.append(f"{name}: majburiy maydon moslanmagan")
    for spec in uses_status_map:
        if not mapping.config.status_map:
            errors.append(f"{spec.name}: status_map sozlamasi bo‘sh")
        bad = sorted(v for v in mapping.config.status_map.values() if v not in spec.enum_values)
        if bad:
            errors.append(f"{spec.name}: status_map’da ruxsat etilmagan qiymatlar: {bad}")
    return errors


def _apply(
    spec: FieldSpec, item: MappingItem, raw: str | None, status_map: dict[str, str]
) -> CanonicalValue:
    if item.transform is Transform.CONST:
        return _parse_const(spec, item.constant)
    value = (raw or "").strip()
    if item.source_column is None or value == "":
        if not spec.nullable:
            raise RowRejected(f"{spec.name}: majburiy maydon bo‘sh")
        return None
    match item.transform:
        case Transform.TEXT:
            _check_value(spec, value, error=RowRejected)
            return value
        case Transform.DECIMAL | Transform.DECIMAL_OR_NULL:
            if not _DECIMAL_RE.fullmatch(value):
                raise RowRejected(f"{spec.name}: son formati noto‘g‘ri: {value!r}")
            return value
        case Transform.DATETIME_TZ:
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as exc:
                raise RowRejected(f"{spec.name}: sana-vaqt ISO 8601 emas: {value!r}") from exc
            if parsed.tzinfo is None or "T" not in value:
                raise RowRejected(f"{spec.name}: vaqt mintaqasi (offset) yo‘q: {value!r}")
            return parsed.isoformat()
        case Transform.DATE:
            if not _DATE_RE.fullmatch(value):
                raise RowRejected(f"{spec.name}: sana YYYY-MM-DD emas: {value!r}")
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError as exc:
                raise RowRejected(f"{spec.name}: mavjud bo‘lmagan sana: {value!r}") from exc
        case Transform.STATUS_MAP:
            mapped = status_map.get(value)
            if mapped is None:
                raise RowRejected(f"{spec.name}: status_map’da yo‘q qiymat: {value!r}")
            _check_value(spec, mapped, error=RowRejected)
            return mapped
    raise RowRejected(f"{spec.name}: noma’lum transform {item.transform}")  # pragma: no cover


def normalize_row(mapping: SourceMapping, row: dict[str, str | None]) -> dict[str, CanonicalValue]:
    """Bitta manba satrini canonical record’ga aylantiradi (maydonlar kontrakt tartibida)."""
    by_field = {i.canonical_field: i for i in mapping.items}
    record: dict[str, CanonicalValue] = {}
    for spec in ENTITY_FIELDS[mapping.entity]:
        item = by_field.get(spec.name)
        if item is None:
            record[spec.name] = None  # validate_mapping faqat nullable maydonni tashlab ketadi
            continue
        raw = row.get(item.source_column) if item.source_column is not None else None
        record[spec.name] = _apply(spec, item, raw, mapping.config.status_map)
    return record
