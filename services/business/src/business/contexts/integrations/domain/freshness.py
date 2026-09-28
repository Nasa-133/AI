"""Ma’lumot yangiligi (TZ I03): Integration Runtime ishlamasa import/sync “kutilmoqda”da qoladi,
dashboardlar esa oxirgi snapshot bo‘yicha ishlaydi, lekin “eskirgan” deb belgilanadi."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

BUSY = frozenset({"discovering", "configuring", "syncing"})
STATUS_TEXT = {"discovering": "fayl o‘qilishi", "configuring": "mapping tekshiruvi",
               "syncing": "sinxronlash"}


@dataclass(frozen=True, slots=True)
class Freshness:
    state: str  # fresh | pending | stale
    message: str | None
    waiting: list[dict[str, Any]]

    def to_json(self) -> dict[str, Any]:
        return {"state": self.state, "message": self.message, "waiting": self.waiting}


def freshness(sources: list[dict[str, Any]], now: datetime, stale_after: timedelta) -> Freshness:
    waiting = []
    for s in sources:
        if s["status"] not in BUSY:
            continue
        seconds = int((now - s["updated_at"]).total_seconds())
        waiting.append({"id": str(s["id"]), "name": s["name"], "status": s["status"],
                        "waiting_seconds": max(seconds, 0),
                        "stale": seconds >= stale_after.total_seconds()})
    stale = [w for w in waiting if w["stale"]]
    if stale:
        w = max(stale, key=lambda x: x["waiting_seconds"])
        minutes = max(w["waiting_seconds"] // 60, 1)
        return Freshness("stale", (
            f"Ma’lumotlar eskirgan bo‘lishi mumkin: “{w['name']}” manbasida "
            f"{STATUS_TEXT.get(w['status'], w['status'])} {minutes} daqiqadan beri kutilmoqda "
            "(integratsiya xizmati javob bermayapti). Dashboardlar oxirgi saqlangan ma’lumot "
            "bo‘yicha ko‘rsatilmoqda."), waiting)
    if waiting:
        return Freshness("pending", "Ma’lumot manbasi yangilanmoqda.", waiting)
    return Freshness("fresh", None, [])
