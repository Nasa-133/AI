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

from ..application.commands import CONVERSATION_PREFIX, USER_LABEL
from ..ports.model import ModelRequest, ModelResponse, ToolCall
from . import fake_documents as docs

_APOSTROPHES = str.maketrans({c: "'" for c in "‘’ʻʼ`´"})

MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6, "iyul": 7,
    "avgust": 8, "sentabr": 9, "sentyabr": 9, "oktabr": 10, "oktyabr": 10, "noyabr": 11,
    "dekabr": 12,
}
# (kalit so‘z, metrika id). Tartib muhim: aniqroq ibora oldin.
METRIC_KEYWORDS: list[tuple[str, str]] = [
    # CRM (voronka) — “savdo” so‘zidan oldin: “bitimlar summasi” savdo tushumi emas.
    ("konversiya", "crm_win_rate"),
    ("yutilgan bitimlar summasi", "crm_won_amount"),
    ("bitimlar summasi", "crm_won_amount"),
    ("o'rtacha bitim", "crm_avg_deal"),
    ("yutilgan bitim", "crm_deals_won"),
    ("ochiq voronka", "crm_pipeline_open"),
    ("voronka", "crm_pipeline_open"),
    ("yangi bitim", "crm_deals_created"),
    ("yangi lid", "crm_deals_created"),
    ("lidlar", "crm_deals_created"),
    ("bitimlar", "crm_deals_created"),
    ("sdelka", "crm_deals_created"),
    ("hujjatlar soni", "order_count"),
    ("hujjat soni", "order_count"),
    ("sotilgan miqdor", "quantity_sold"),
    ("tannarx", "cogs"),
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
    ("bosqich", "stage"),
    ("kanal", "channel"),
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
MAX_QUERY_METRICS = 6  # run_metric_query chegarasi
_TOP_RE = re.compile(r"(?:\btop\s*(?P<n>\d{1,3})?|eng (?:ko'p|yuqori|katta|yaxshi)|"
                     r"(?P<low>eng (?:kam|past|yomon|kichik))|(?P<n2>\d{1,3}) ta eng)")
_CLARIFICATION_RE = re.compile(r"qaysi (ko'rsatkich|biri) kerak")
_ALL_RE = re.compile(r"^(barchasi|hammasi|hamma|barcha|hammasini|barchasini)\W*$")
# “Barchasi” — katalogdagi savdo ko‘rsatkichlari (build_plan katalog bo‘yicha ochadi).
_ALL_MARKER = "barcha ko'rsatkichlar"


def metric_kind(metric_id: str) -> str:
    """Manba turi (Core QuerySpec.kind bilan mos): savdo, debitorlik yoki CRM."""
    if metric_id.startswith("receivables_"):
        return "receivable"
    return "crm" if metric_id.startswith("crm_") else "sales"


_REFERENCE_RE = re.compile(r"\b(shu|bu|ushbu|yuqoridagi|tepadagi|oldingi)\b")
_QUERY_REF_RE = re.compile(r"- (Query|Taqqoslash query): `([0-9a-f-]{36})`")
_ADDRESS_RE = re.compile(r"^\s*@?[\w']+\s*,\s*")


def referenced_report(text: str, turns: list[tuple[str, str]],
                      ) -> tuple[str, list[tuple[str, str]]] | None:
    """“Shu hisobot bo‘yicha dashboard” — metrika aytilmagan, oldingi javobga ishora.

    Oldingi agent javobining manbalaridagi query ID’lari qaytariladi: dashboard qayta hisoblamasdan
    aynan o‘sha natijaga bog‘lanadi (raqamlar chatdagi bilan bir xil)."""
    t = normalize(text)
    if not _DASHBOARD_RE.search(t) or not _REFERENCE_RE.search(t):
        return None
    if any(keyword in t for keyword, _ in METRIC_KEYWORDS):
        return None  # ko‘rsatkich aniq aytilgan — oddiy yo‘l
    for i in range(len(turns) - 1, -1, -1):
        role, body = turns[i]
        refs = _QUERY_REF_RE.findall(body) if role == "agent" else []
        if refs:
            question = next((turns[j][1] for j in range(i - 1, -1, -1) if turns[j][0] == "user"),
                            "Hisobot")
            return question, refs
    return None


def report_title(question: str) -> str:
    title = _ADDRESS_RE.sub("", question, count=1).strip().rstrip("?.!") or "Hisobot"
    return (title[0].upper() + title[1:])[:200]


def conversation_turns(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Developer “Oldingi suhbat” xabaridan (rol, matn) juftlari; ko‘p qatorli matn birlashadi."""
    content = next((str(i["content"]) for i in items
                    if i.get("role") == "developer"
                    and str(i.get("content", "")).startswith(CONVERSATION_PREFIX)), "")
    turns: list[tuple[str, str]] = []
    for line in content.splitlines()[1:]:
        m = re.match(r"^\[(.+?)\]: ?(.*)$", line)
        if m:
            turns.append(("user" if m.group(1) == USER_LABEL else "agent", m.group(2)))
        elif turns:
            turns[-1] = (turns[-1][0], f"{turns[-1][1]}\n{line}")
    return turns


def resolve_followup(text: str, turns: list[tuple[str, str]]) -> str:
    """Aniqlashtiruvchi savolga javob (“barchasi”, metrikalar ro‘yxati) boshlang‘ich so‘rovga
    qo‘shiladi: davr, kesim va dashboard talabi o‘sha so‘rovdan olinadi."""
    chain: list[str] = []
    i = len(turns) - 1
    while i >= 1 and turns[i][0] == "agent" and _CLARIFICATION_RE.search(normalize(turns[i][1])) \
            and turns[i - 1][0] == "user":
        chain.insert(0, turns[i - 1][1])
        i -= 2
    if not chain:
        return text
    answer = _ALL_MARKER if _ALL_RE.match(normalize(text)) else text
    return " ".join([*(c for c in chain if not _ALL_RE.match(normalize(c))), answer])


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
    order_by: dict[str, str] | None = None
    limit: int | None = None
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
    if _ALL_MARKER in t:  # “barchasi”: katalogdagi savdo ko‘rsatkichlari
        requested = list(dict.fromkeys(
            [*requested, *(m for m in metrics if metric_kind(m) == "sales")]))
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
    # Savdo, debitorlik va CRM metrikalari bitta so‘rovda aralashtirilmaydi (Core qoidasi).
    kind = metric_kind(requested[0])
    same = [m for m in requested if metric_kind(m) == kind]
    other = [metrics[m]["name"] for m in requested if m not in same]
    if other:
        plan.notes.append("Boshqa manbadagi ko‘rsatkichlar alohida so‘rov bilan: "
                          + ", ".join(other) + ".")
    if len(same) > MAX_QUERY_METRICS:
        plan.notes.append(f"Bir so‘rovda ko‘pi bilan {MAX_QUERY_METRICS} ta ko‘rsatkich: "
                          + ", ".join(metrics[m]["name"] for m in same[MAX_QUERY_METRICS:])
                          + " keyingi so‘rovda.")
    plan.metric_ids = same[:MAX_QUERY_METRICS]
    if "gross_profit" in plan.metric_ids and "yalpi" not in t:
        plan.notes.append("“Foyda” deganda yalpi foyda olindi (sof foyda hisoblanmaydi).")

    allowed_dims = {d for m in plan.metric_ids for d in metrics[m].get("dimensions", [])}
    # Metrika nomlari (“Sotilgan mahsulot tannarxi”) kesim so‘zi deb o‘qilmasin.
    t_dims = t
    for m in metrics.values():
        t_dims = t_dims.replace(normalize(str(m.get("name", ""))), " ")
    for keyword, dim in DIMENSION_KEYWORDS:
        if keyword in t_dims and dim not in plan.dimensions:
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
    # “Top 10 mahsulot”, “eng ko‘p sotilgan”, “eng past marja” — birinchi metrika bo‘yicha saralash.
    if plan.dimensions and (m := _TOP_RE.search(t)):
        plan.order_by = {"metric_id": plan.metric_ids[0],
                         "direction": "asc" if m.group("low") else "desc"}
        count = m.group("n") or m.group("n2")
        plan.limit = max(1, min(int(count), 100)) if count else 10
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
    if len(plan.metric_ids) > 1:
        metric += f" va yana {len(plan.metric_ids) - 1} ko‘rsatkich"
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
        original = text
        text = resolve_followup(text, conversation_turns(request.items))
        calls = {i["call_id"]: i for i in request.items if i.get("type") == "function_call"}
        outputs: dict[str, dict[str, Any]] = {}
        for item in request.items:
            if item.get("type") == "function_call_output" and item["call_id"] in calls:
                outputs[calls[item["call_id"]]["name"]] = json.loads(item["output"])
        available = {t.name for t in request.tools}
        report = referenced_report(original, conversation_turns(request.items))
        if report is not None and "create_dashboard" in available:
            return self._report_dashboard(request, report, outputs, available)
        context_ids = docs.context_document_ids(request.items)
        if docs.is_document_request(text, available, bool(context_ids)):
            return self._documents(request, text, context_ids, available)

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
                "currency": plan.currency, "limit": plan.limit,
                "order_by": plan.order_by}, available)
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
            # KPI — faqat bitta ko‘rsatkich va bitta qator (bir valyuta); aks holda jadval.
            single = len(plan.metric_ids) == 1 and len(query["data"]["rows"]) == 1
            chart = ("line" if plan.dimensions and plan.dimensions[0] in ("month", "day")
                     else "bar" if plan.dimensions else "kpi" if single else "table")
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
        failed = outputs.get("create_dashboard")
        if plan.dashboard and failed is not None and failed["status"] != "ok":
            # So‘ralgan dashboard chiqmagan bo‘lsa, javob buni ochiq aytadi (jim o‘tib ketmaydi).
            answer += ("\n- Dashboard yaratilmadi: "
                       f"{failed.get('error_message') or failed.get('error_code')}.")
        return self._final(request, answer, partial=bool(limitations), limitations=limitations)

    def _report_dashboard(self, request: ModelRequest,
                          report: tuple[str, list[tuple[str, str]]],
                          outputs: dict[str, dict[str, Any]], available: set[str]) -> ModelResponse:
        question, refs = report
        title = report_title(question)
        if "create_dashboard" not in outputs:
            widgets = [{"title": "Oldingi davr bilan taqqoslash" if kind.startswith("Taqqoslash")
                        else "Hisobot natijasi", "type": "table", "query_spec_id": qid,
                        "text": None} for kind, qid in refs]
            return self._call(request, "create_dashboard", {
                "title": title, "description": f"Chatdagi hisobot asosida: “{question}”.",
                "widgets": widgets}, available)
        result = outputs["create_dashboard"]
        if result["status"] != "ok":
            return self._final(request, self._tool_error_text(result), partial=True)
        d = result["data"]
        return self._final(request, "\n".join([
            "**Qisqa javob**",
            f"Dashboard yaratildi: **{d['title']}** ({d['widget_count']} ta widget) — oldingi "
            "hisobot natijalari asosida, raqamlar chatdagi javob bilan bir xil.",
            "", "**Harakat variantlari**",
            "- Dashboardni ochib turini (jadval, grafik) o‘zgartirish — “Tahrirlash”.",
            "- Oxirgi ma’lumot bilan qayta hisoblash — “Yangilash”.",
            "", "**Manbalar va cheklovlar**",
            *(f"- {kind}: `{qid}`" for kind, qid in refs),
            f"- Dashboard: `{d['dashboard_id']}`, versiya {d['version']}.",
        ]))

    # --- javob elementlari -------------------------------------------------------------
    def _documents(self, request: ModelRequest, text: str, context_ids: list[str],
                   available: set[str]) -> ModelResponse:
        calls = {i["call_id"]: i for i in request.items if i.get("type") == "function_call"}
        done: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
            (calls[i["call_id"]]["name"], json.loads(calls[i["call_id"]]["arguments"]),
             json.loads(i["output"]))
            for i in request.items
            if i.get("type") == "function_call_output" and i["call_id"] in calls]
        last = {name: result for name, _, result in done}
        if "search_documents" not in last:
            return self._call(request, "search_documents", {
                "query": docs.search_query(text), "document_ids": context_ids or None,
                "limit": 8}, available)
        search = last["search_documents"]
        if search["status"] != "ok":
            return self._final(request, self._tool_error_text(search), partial=True)
        edit = docs.parse_edit(text)
        if edit is None:
            answer, found = docs.answer_question(text, search["data"])
            return self._final(request, answer,
                               limitations=[] if found else ["Hujjatda topilmadi"])

        candidates = docs.edit_candidates(edit, search["data"])
        by_doc = {h["document_id"]: h for h in candidates}
        if "create_document_draft" in last:
            draft = last["create_document_draft"]
            if draft["status"] != "ok":
                return self._final(request, self._tool_error_text(draft), partial=True)
            hit = by_doc.get(draft["data"]["document_id"]) or candidates[0]
            return self._final(request, docs.draft_answer(draft["data"], hit))
        if not candidates:
            return self._final(request, f"“{edit.find}” matni hujjatda topilmadi — "
                               "o‘zgartirish taklif qilinmadi.",
                               limitations=["Hujjatda topilmadi"])
        # Joylar: bitta bo‘limli parcha — bo‘lim ma’lum; ko‘p bo‘limli — bo‘limlar o‘qiladi.
        read = {(a["version_id"], a["section_id"]): r for n, a, r in done
                if n == "read_document_section"}
        places: dict[tuple[str, str], tuple[dict[str, Any], int]] = {}
        for hit in candidates:
            if len(hit["section_ids"]) == 1:
                key = (hit["version_id"], hit["section_ids"][0])
                places[key] = (hit, max(places.get(key, (hit, 0))[1],
                                        docs.count(hit["text"], edit.find)))
                continue
            for sid in hit["section_ids"][:10]:
                result = read.get((hit["version_id"], sid))
                if result is None:
                    return self._call(request, "read_document_section", {
                        "document_id": hit["document_id"], "version_id": hit["version_id"],
                        "section_id": sid}, available)
                if result["status"] == "ok" and (n := docs.count(result["data"]["text"],
                                                                 edit.find)):
                    places[(hit["version_id"], sid)] = (
                        {**hit, "locator": result["data"]["locator"]}, n)
        if len(places) != 1 or next(iter(places.values()))[1] > 1:
            hits = [h for h, _ in places.values()] or candidates
            return self._final(request, docs.ambiguity_question(edit, hits),
                               clarification=True)
        (_, section_id), (hit, _) = next(iter(places.items()))
        return self._call(request, "create_document_draft",
                          docs.draft_arguments(hit, section_id, edit), available)

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
        reason = str(result.get("error_message") or result.get("error_code")).rstrip(". ")
        return f"Hisoblab bo‘lmadi. {reason}. Raqam taxmin qilinmadi."
