"""Foydalanuvchi tahriri: nom, tavsif, widget tartibi/turi/o‘chirish → yangi versiya.

Yangi raqam yoki begona query qo‘shib bo‘lmaydi: faqat mavjud widget’lar qayta joylanadi.
"""

from typing import Any
from uuid import UUID

from .spec import DashboardSpec, InvalidDashboard, Widget, WidgetType


def apply_edit(current: dict[str, Any], *, title: str | None, description: str | None,
               widgets: list[dict[str, Any]] | None) -> DashboardSpec:
    existing = {w["id"]: w for w in current["widgets"]}
    new_widgets: list[Widget] = []
    for item in widgets if widgets is not None else current["widgets"]:
        base = existing.get(item["id"])
        if base is None:
            raise InvalidDashboard(f"Noma’lum widget: {item['id']}")
        new_widgets.append(Widget(
            id=base["id"],
            title=(item.get("title") or base["title"]).strip()[:200],
            type=WidgetType(item.get("type") or base["type"]),
            query_spec_id=UUID(base["query_spec_id"]) if base["query_spec_id"] else None,
            text=base["text"],
        ))
    if len({w.id for w in new_widgets}) != len(new_widgets):
        raise InvalidDashboard("Widget takrorlanmasin.")
    return DashboardSpec(
        title=(title if title is not None else current["title"]).strip(),
        description=description if description is not None else current["description"],
        widgets=tuple(new_widgets),
    )
