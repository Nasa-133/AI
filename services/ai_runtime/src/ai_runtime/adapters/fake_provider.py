"""Deterministik “model”: o‘zbekcha (lotin) analitik so‘rovlar uchun qoidaga asoslangan reja.

Testlar va demo uchun. Haqiqiy model o‘rnini bosmaydi, lekin xuddi shu tool loop
kontraktidan o‘tadi: vositalarni chaqiradi va javobni faqat vosita natijalaridan tuzadi.
"""

import calendar
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from ..ports.model import ModelRequest, ModelResponse, ToolCall

_APOSTROPHES = str.maketrans({c: "'" for c in "‘’ʻʼ`´"})

MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6, "iyul": 7,
    "avgust": 8, "sentabr": 9, "sentyabr": 9, "oktabr": 10, "oktyabr": 10, "noyabr": 11,
    "dekabr": 12,
}
# (kalit so‘z, metrika id). Tartib muhim: aniqroq ibora oldin.
METRIC_KEYWORDS: list[tuple[str, str]] = [
    ("sof foyda", "net_profit"),
    ("marja", "gross_margin"),
    ("yalpi foyda", "gross_profit"),
    ("foyda", "gross_profit"),
    ("muddati o'tgan", "receivables_overdue"),
    ("debitor", "receivables_open"),
    ("qarz", "receivables_open"),
    ("chegirma", "discounts"),
    ("qaytarish", "returns"),
    ("tushum", "net_sales"),
    ("savdo", "net_sales"),
    ("sotuv", "net_sales"),
]
DIMENSION_KEYWORDS: list[tuple[str, str]] = [
    ("filial", "branch"),
    ("mahsulot", "product"),
    ("tovar", "product"),
    ("mijoz", "customer"),
    ("oylar bo'yicha", "month"),
    ("oyma-oy", "month"),
    ("har oy", "month"),
    ("kunlar bo'yicha", "day"),
]
_COMPARE_WORDS = ("solishtir", "taqqosla", "nega", "kamay", "oshdi", "o'sdi", "o'zgar")
_EXPLAIN_WORDS = ("nega", "sabab", "nima uchun")
_DASHBOARD_RE = re.compile(r"(dashboard|dashbord|doska)")


def normalize(text: str) -> str:
    return " ".join(text.translate(_APOSTROPHES).lower().split())


@dataclass(frozen=True, slots=True)
class Period:
    start: date
    end: date

    def as_args(self) -> dict[str, str]:
        return {"from": self.start.isoformat(), "to": self.end.isoformat()}

    def previous(self) -> "Period":
        """To‘liq oylardan iborat davr uchun — oldingi shuncha to‘liq oy; aks holda oldingi
        teng uzunlikdagi davr."""
        if self.start.day == 1 and self.end == _month_end(self.end):
            months = (self.end.year - self.start.year) * 12 + self.end.month - self.start.month + 1
            return Period(_add_months(self.start, -months), self.start - timedelta(days=1))
        if self.start.day == 1 and self.start.month == self.end.month:
            # MTD: oldingi oyning mos kunlari (TZ 7.1).
            prev = _add_months(self.start, -1)
            end = date(prev.year, prev.month, min(self.end.day, _month_end(prev).day))
            return Period(prev, end)
        length = (self.end - self.start).days + 1
        prev_end = self.start - timedelta(days=1)
        return Period(prev_end - timedelta(days=length - 1), prev_end)


def _month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _add_months(d: date, months: int) -> date:
    index = d.year * 12 + d.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def resolve_period(text: str, today: date) -> tuple[Period, list[str]]:
    """Matndagi davrni korxona vaqt mintaqasidagi `today` bo‘yicha yechadi."""
    t = normalize(text)
    this_month = today.replace(day=1)
    if "o'tgan oy" in t:
        start = _add_months(this_month, -1)
        return Period(start, _month_end(start)), []
    if "bu oy" in t or "joriy oy" in t:
        return Period(this_month, today), ["Joriy oy to‘liq emas (oy boshidan bugungacha)."]
    if m := re.search(r"oxirgi (\d{1,2}) oy", t):
        n = max(1, min(int(m.group(1)), 24))
        start = _add_months(this_month, -n)
        return Period(start, this_month - timedelta(days=1)), []
    if "o'tgan yil" in t:
        return Period(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)), []
    if "bu yil" in t:
        return Period(date(today.year, 1, 1), today), ["Joriy yil to‘liq emas."]
    names = "|".join(MONTHS)
    if m := re.search(rf"\b({names})\w*\s*(?:dan|-|–|—)\s*({names})\w*", t):
        first, last = MONTHS[m.group(1)], MONTHS[m.group(2)]
        year_match = re.search(r"\b(20\d{2})\b", t)
        year = int(year_match.group(1)) if year_match else today.year
        start, end = date(year, first, 1), _month_end(date(year, last, 1))
        if end < start:
            end = _month_end(date(year + 1, last, 1))  # masalan, noyabrdan fevralgacha
        notes = []
        if end > today:
            end, notes = today, ["Davr bugungacha qisqartirildi."]
        return Period(start, end), notes
    for name, month in MONTHS.items():
        if re.search(rf"\b{name}", t):
            year_match = re.search(r"\b(20\d{2})\b", t)
            if year_match:
                year = int(year_match.group(1))
            else:
                year = today.year if month <= today.month else today.year - 1
            start = date(year, month, 1)
            end = min(_month_end(start), today) if start <= today else _month_end(start)
            notes = ["Oy to‘liq emas (bugungacha)."] if end < _month_end(start) else []
            return Period(start, end), notes
    start = _add_months(this_month, -1)
    return Period(start, _month_end(start)), ["Davr ko‘rsatilmagan: oxirgi to‘liq oy olindi."]


@dataclass(slots=True)
class Plan:
    metric_ids: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    period: Period | None = None
    currency: str | None = None
    compare: bool = False
    explain: bool = False
    dashboard: bool = False
    notes: list[str] = field(default_factory=list)
    clarification: str | None = None


def build_plan(text: str, catalog: dict[str, Any]) -> Plan:
    t = normalize(text)
    plan = Plan()
    metrics = {m["id"]: m for m in catalog.get("metrics", [])}

    found: list[tuple[int, str]] = []
    consumed = t
    for keyword, metric_id in METRIC_KEYWORDS:
        pos = consumed.find(keyword)
        if pos >= 0:
            found.append((pos, metric_id))
            consumed = consumed.replace(keyword, " " * len(keyword))
    requested = list(dict.fromkeys(mid for _, mid in sorted(found)))
    if not requested:
        names = ", ".join(m["name"] for m in metrics.values()) or "—"
        plan.clarification = f"Qaysi ko‘rsatkich kerak? Mavjud metrikalar: {names}."
        return plan
    missing = [m for m in requested if m not in metrics]
    if "net_profit" in missing and "gross_profit" in metrics:
        plan.clarification = ("Sof foyda uchun xarajatlar va hisob siyosati ma’lumoti yo‘q, "
                              "shuning uchun uni hisoblamayman. Yalpi foydani ko‘rsataymi?")
        return plan
    if missing:
        names = ", ".join(m["name"] for m in metrics.values()) or "—"
        plan.clarification = (f"So‘ralgan ko‘rsatkich hozir mavjud emas. Mavjud metrikalar: "
                              f"{names}. Qaysi biri kerak?")
        return plan
    plan.metric_ids = requested[:3]
    if "gross_profit" in plan.metric_ids and "yalpi" not in t:
        plan.notes.append("“Foyda” deganda yalpi foyda olindi (sof foyda hisoblanmaydi).")

    allowed_dims = {d for m in plan.metric_ids for d in metrics[m].get("dimensions", [])}
    for keyword, dim in DIMENSION_KEYWORDS:
        if keyword in t and dim not in plan.dimensions:
            if dim in allowed_dims:
                plan.dimensions.append(dim)
            else:
                plan.notes.append(f"Tanlangan metrika uchun “{keyword}” kesimi mavjud emas.")
    plan.dimensions = plan.dimensions[:2]

    today = date.fromisoformat(catalog["today"])
    plan.period, period_notes = resolve_period(text, today)
    plan.notes.extend(period_notes)
    coverage_to = (catalog.get("data_coverage") or {}).get("to")
    if coverage_to and plan.period.start > date.fromisoformat(coverage_to):
        plan.notes.append("Tanlangan davr uchun ma’lumot hali yuklanmagan bo‘lishi mumkin.")

    if "dollar" in t or "usd" in t:
        plan.currency = "USD"
    elif "so'm" in t or "uzs" in t:
        plan.currency = "UZS"
    elif len(catalog.get("currencies", [])) == 1:
        plan.currency = catalog["currencies"][0]

    plan.explain = any(w in t for w in _EXPLAIN_WORDS)
    plan.compare = plan.explain or any(w in t for w in _COMPARE_WORDS)
    plan.dashboard = bool(_DASHBOARD_RE.search(t))
    return plan


# --- javob tuzish (faqat vosita natijalaridagi raqamlar) ----------------------------------
def _cell(value: Any) -> str:
    return "—" if value is None else str(value).replace("|", "/")


DIMENSION_NAMES = {"month": "Oy", "week": "Hafta", "day": "Kun", "branch": "Filial",
                   "product": "Mahsulot", "customer": "Mijoz", "currency": "Valyuta"}
_KIND_SUFFIX = {"current": "joriy", "previous": "oldingi", "abs_change": "farq",
                "pct_change": "o‘zgarish, %"}


def _header(column: dict[str, Any], names: dict[str, str]) -> str:
    if column.get("kind") == "dimension":
        if column["name"].endswith("_name"):
            return "Nomi"
        return DIMENSION_NAMES.get(str(column["name"]), str(column["name"]))
    base: str = names.get(column.get("metric_id") or "", str(column["name"]))
    suffix = _KIND_SUFFIX.get(column.get("kind", ""))
    return f"{base} ({suffix})" if suffix else base


def _table(columns: list[dict[str, Any]], rows: list[list[Any]], limit: int = 15,
           names: dict[str, str] | None = None) -> str:
    header = "| " + " | ".join(_cell(_header(c, names or {})) for c in columns) + " |"
    sep = "|" + "---|" * len(columns)
    body = ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows[:limit]]
    extra = ["", "_Qolgan satrlar to‘liq jadvalda (query manbasi)._"] if len(rows) > limit else []
    return "\n".join([header, sep, *body, *extra])


def _dec(value: Any) -> Decimal | None:
    try:
        return None if value is None else Decimal(str(value))
    except InvalidOperation:
        return None


def dashboard_title(plan: Plan, catalog: dict[str, Any], query: dict[str, Any]) -> str:
    """Masalan: “Sof savdo tushumi — oylar kesimida, 2026-01-01 — 2026-04-30”."""
    names = {m["id"]: m["name"] for m in catalog.get("metrics", [])}
    metric = names.get(plan.metric_ids[0], plan.metric_ids[0])
    dims = [DIMENSION_NAMES.get(d, d).lower() for d in plan.dimensions]
    period = query["period"]
    by = f" — {', '.join(dims)} kesimida" if dims else ""
    return f"{metric}{by}, {period['from']} — {period['to']}"[:200]


def compose_answer(plan: Plan, catalog: dict[str, Any],
                   results: dict[str, dict[str, Any]]) -> str:
    metrics = {m["id"]: m for m in catalog.get("metrics", [])}
    names = {mid: m["name"] for mid, m in metrics.items()}
    query = results["run_metric_query"]
    compare = results.get("compare_periods")
    explain = results.get("explain_contributions")
    dashboard = results.get("create_dashboard")
    period = query["period"]
    currency = query.get("currency") or "valyuta bo‘yicha ajratilgan"
    first_metric = plan.metric_ids[0]
    metric_name = metrics[first_metric]["name"]
    metric_col = next((i for i, c in enumerate(query["columns"])
                       if c["kind"] == "metric" and c["metric_id"] == first_metric), None)
    dim_cols = [i for i, c in enumerate(query["columns"]) if c["kind"] == "dimension"]

    short: list[str] = []
    if not query["rows"] or metric_col is None:
        short.append(f"{period['from']} — {period['to']} davrida {metric_name} bo‘yicha "
                     f"ma’lumot topilmadi.")
    elif not dim_cols:
        value = query["rows"][0][metric_col]
        short.append(f"{period['from']} — {period['to']}: {metric_name} — {_cell(value)} "
                     f"({currency}).")
    else:
        ranked = [r for r in query["rows"] if _dec(r[metric_col]) is not None]
        if ranked:
            top = max(ranked, key=lambda r: _dec(r[metric_col]) or Decimal(0))
            member = " / ".join(_cell(top[i]) for i in dim_cols)
            short.append(f"{period['from']} — {period['to']}: {metric_name} bo‘yicha eng "
                         f"yuqori natija — {member} ({_cell(top[metric_col])}, {currency}).")
    if explain:
        contributions = explain.get("contributions", [])
        if contributions:
            biggest = max(contributions,
                          key=lambda c: abs(_dec(c["change"]) or Decimal(0)))
            share = biggest.get("share_of_change_pct")
            share_text = f", umumiy o‘zgarishning {share}%" if share is not None else ""
            short.append(f"Umumiy o‘zgarish: {explain['total_change']}. Eng katta hisobiy hissa "
                         f"— {biggest['member']} ({biggest['change']}{share_text}).")

    parts = ["**Qisqa javob**", " ".join(short), "", "**Asosiy raqamlar**",
             _table(query["columns"], query["rows"], names=names)]
    if compare:
        parts += ["", "**Taqqoslash** (oldingi davr: "
                  f"{compare['comparison_period']['from']} — {compare['comparison_period']['to']})",
                  _table(compare["columns"], compare["rows"], names=names)]
    if explain:
        rows = [[c["member"], c["current"], c["previous"], c["change"], c["share_of_change_pct"]]
                for c in explain.get("contributions", [])]
        cols = [{"name": n} for n in ("kesim", "joriy", "oldingi", "o‘zgarish", "ulush %")]
        parts += ["", "**Tekshirilgan omillar (hisobiy hissa)**", _table(cols, rows),
                  "Bu hisobiy hissa: qaysi kesim o‘zgarishga qancha qo‘shganini ko‘rsatadi, "
                  "sababni isbotlamaydi.",
                  "", "**Gipotezalar**",
                  "- Gipoteza: o‘zgarish narx, assortiment yoki talab bilan bog‘liq bo‘lishi "
                  "mumkin — mavjud ma’lumot buni tasdiqlamaydi; mahsulot kesimida qo‘shimcha "
                  "tahlil kerak."]
    parts += ["", "**Harakat variantlari**"]
    if explain:
        parts.append("- Eng katta hissa qo‘shgan kesimni mahsulotlar bo‘yicha batafsil ko‘rish.")
    if not dashboard:
        parts.append("- Ko‘rsatkichni muntazam kuzatish uchun dashboard yaratish.")
    parts.append("- Natijani mijozning tasdiqlangan hisoboti bilan solishtirib tekshirish.")

    parts += ["", "**Manbalar va cheklovlar**"]
    snapshots: list[str] = []
    for result in (query, compare, explain):
        if result:
            snapshots += [s for s in result.get("dataset_snapshot_ids", []) if s not in snapshots]
    parts += [f"- Dataset snapshot: `{s}`" for s in snapshots]
    parts.append(f"- Query: `{query['query_spec_id']}`; davr: {period['from']} — {period['to']}; "
                 f"valyuta: {currency}; hisoblangan: {query['as_of']}")
    if compare:
        parts.append(f"- Taqqoslash query: `{compare['query_spec_id']}`")
    if dashboard:
        parts.append(f"- Dashboard yaratildi: {dashboard['title']} (`{dashboard['dashboard_id']}`"
                     f", versiya {dashboard['version']}). Ofis doskasida ochish mumkin.")
    for note in plan.notes:
        parts.append(f"- {note}")
    for result in (query, compare, explain):
        if result:
            parts += [f"- {n}" for n in result.get("notes", [])]
    return "\n".join(parts)


class FakeProvider:
    """ModelProvider: har chaqiruvda suhbat holatidan keyingi qadamni tanlaydi."""

    name = "fake"

    async def respond(self, request: ModelRequest) -> ModelResponse:
        text = next((str(i["content"]) for i in request.items
                     if i.get("type") == "message" and i.get("role") == "user"), "")
        calls = {i["call_id"]: i for i in request.items if i.get("type") == "function_call"}
        outputs: dict[str, dict[str, Any]] = {}
        for item in request.items:
            if item.get("type") == "function_call_output" and item["call_id"] in calls:
                outputs[calls[item["call_id"]]["name"]] = json.loads(item["output"])
        available = {t.name for t in request.tools}

        if "list_available_metrics" not in outputs:
            return self._call(request, "list_available_metrics", {"subject": "all"}, available)
        catalog_result = outputs["list_available_metrics"]
        if catalog_result["status"] != "ok":
            return self._final(request, self._tool_error_text(catalog_result), partial=True)
        catalog = catalog_result["data"]
        plan = build_plan(text, catalog)
        if plan.clarification:
            return self._final(request, plan.clarification, clarification=True)
        assert plan.period is not None

        if "run_metric_query" not in outputs:
            return self._call(request, "run_metric_query", {
                "metric_ids": plan.metric_ids, "date_range": plan.period.as_args(),
                "dimensions": plan.dimensions,
                "filters": {"branch_codes": None, "product_codes": None, "customer_codes": None},
                "currency": plan.currency, "limit": None}, available)
        query = outputs["run_metric_query"]
        if query["status"] != "ok":
            return self._final(request, self._tool_error_text(query), partial=True)
        spec_id = query["data"]["query_spec_id"]
        comparison = plan.period.previous().as_args()

        if plan.compare and "compare_periods" not in outputs:
            return self._call(request, "compare_periods",
                              {"query_spec_id": spec_id, "comparison_range": comparison},
                              available)
        if plan.explain and "explain_contributions" not in outputs:
            dimension = next((d for d in plan.dimensions if d in ("branch", "product",
                                                                   "customer")), "branch")
            return self._call(request, "explain_contributions", {
                "query_spec_id": spec_id, "comparison_range": comparison,
                "dimension": dimension, "metric_id": plan.metric_ids[0]}, available)
        if plan.dashboard and "create_dashboard" not in outputs:
            chart = ("line" if plan.dimensions and plan.dimensions[0] in ("month", "day")
                     else "bar" if plan.dimensions else "kpi")
            widgets = [{"title": "Asosiy ko‘rsatkich", "type": chart,
                        "query_spec_id": spec_id, "text": None}]
            if "compare_periods" in outputs and outputs["compare_periods"]["status"] == "ok":
                widgets.append({"title": "Oldingi davr bilan taqqoslash", "type": "table",
                                "query_spec_id": outputs["compare_periods"]["data"][
                                    "query_spec_id"], "text": None})
            return self._call(request, "create_dashboard", {
                "title": dashboard_title(plan, catalog, outputs["run_metric_query"]["data"]),
                "description": None, "widgets": widgets}, available)

        results = {name: r["data"] for name, r in outputs.items() if r["status"] == "ok"}
        limitations = [f"{name}: {r.get('error_message') or r.get('error_code')}"
                       for name, r in outputs.items() if r["status"] != "ok"]
        answer = compose_answer(plan, catalog, results)
        return self._final(request, answer, partial=bool(limitations), limitations=limitations)

    # --- javob elementlari -------------------------------------------------------------
    @staticmethod
    def _usage(request: ModelRequest, out: str) -> tuple[int, int]:
        return len(json.dumps(request.items, ensure_ascii=False)) // 4, len(out) // 4

    def _call(self, request: ModelRequest, name: str, arguments: dict[str, Any],
              available: set[str]) -> ModelResponse:
        if name not in available:
            return self._final(request, f"`{name}` vositasi bu agent uchun mavjud emas.",
                               partial=True)
        n = sum(1 for i in request.items if i.get("type") == "function_call") + 1
        call_id = f"call_{n:02d}_{name}"
        args = json.dumps(arguments, ensure_ascii=False)
        item = {"type": "function_call", "call_id": call_id, "name": name, "arguments": args}
        tokens_in, tokens_out = self._usage(request, args)
        return ModelResponse(status="completed", output_items=[item], text=None,
                             tool_calls=[ToolCall(call_id, name, args)],
                             input_tokens=tokens_in, output_tokens=tokens_out)

    def _final(self, request: ModelRequest, text: str, *, partial: bool = False,
               clarification: bool = False, limitations: list[str] | None = None,
               ) -> ModelResponse:
        tokens_in, tokens_out = self._usage(request, text)
        return ModelResponse(
            status="incomplete" if partial else "completed",
            output_items=[{"type": "message", "role": "assistant",
                           "content": [{"type": "output_text", "text": text}]}],
            text=text, tool_calls=[], input_tokens=tokens_in, output_tokens=tokens_out,
            needs_clarification=clarification, limitations=list(limitations or []))

    @staticmethod
    def _tool_error_text(result: dict[str, Any]) -> str:
        return ("Hisoblash vositasi natija bermadi: "
                f"{result.get('error_message') or result.get('error_code')}. "
                "Raqam taxmin qilinmadi.")
