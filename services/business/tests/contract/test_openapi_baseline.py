"""Joriy Business API spetsifikatsiyasi review qilingan baseline bilan mos (TZ 13.11, gate 3).

Breaking o‘zgarish — test yiqiladi (yangi major versiya va migratsiya rejasi kerak).
Mos (non-breaking) o‘zgarish — baseline yangilanmaguncha test yiqiladi, shunda har API
o‘zgarishi PR’da ko‘rinadigan diff sifatida review’dan o‘tadi.
"""

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
BASELINE = REPO / "contracts" / "http" / "business.openapi.json"
sys.path.insert(0, str(REPO / "tools" / "contracts"))

from export_openapi import build_openapi, render  # noqa: E402
from openapi_diff import compare  # noqa: E402

REGENERATE = (
    "cd services/business && uv run python ../../tools/contracts/export_openapi.py business"
    " > ../../contracts/http/business.openapi.json"
)


def _current() -> dict[str, Any]:
    # JSON orqali o‘tkazish: baseline bilan bir xil ko‘rinishda solishtirish uchun.
    result: dict[str, Any] = json.loads(render(build_openapi("business")))
    return result


def test_no_breaking_changes_against_baseline() -> None:
    report = compare(json.loads(BASELINE.read_text(encoding="utf-8")), _current())
    assert not report.breaking, (
        "Business API’da breaking o‘zgarish:\n  "
        + "\n  ".join(report.breaking)
        + "\nYangi major versiya kerak (TZ 13.11) yoki o‘zgarishni moslang."
    )


def test_baseline_is_up_to_date() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = _current()
    if baseline == current:
        return
    report = compare(baseline, current)
    details = "\n  ".join(report.non_breaking) or "(faqat metadata)"
    raise AssertionError(
        "OpenAPI baseline eskirgan. O‘zgarishlar:\n  "
        + details
        + f"\nReview’dan keyin baseline’ni yangilang:\n  {REGENERATE}"
    )
