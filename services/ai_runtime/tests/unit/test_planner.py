from datetime import date

import pytest

from ai_runtime.adapters.fake_provider import Period, build_plan, resolve_period
from tests.fake_core import default_data

TODAY = date(2026, 9, 27)
CATALOG = default_data()["list_available_metrics"]


@pytest.mark.parametrize(("text", "start", "end"), [
    ("O‘tgan oy filiallar savdosini solishtir", date(2026, 8, 1), date(2026, 8, 31)),
    ("o'tgan oy", date(2026, 8, 1), date(2026, 8, 31)),
    ("bu oy tushum", date(2026, 9, 1), date(2026, 9, 27)),
    ("2026 iyun savdosi", date(2026, 6, 1), date(2026, 6, 30)),
    ("iyun", date(2026, 6, 1), date(2026, 6, 30)),
    ("dekabr savdosi", date(2025, 12, 1), date(2025, 12, 31)),
    ("oxirgi 3 oy", date(2026, 6, 1), date(2026, 8, 31)),
    ("savdo qancha", date(2026, 8, 1), date(2026, 8, 31)),
])
def test_resolve_period(text: str, start: date, end: date) -> None:
    period, _ = resolve_period(text, TODAY)
    assert (period.start, period.end) == (start, end)


def test_incomplete_current_month_is_flagged() -> None:
    _, notes = resolve_period("bu oy", TODAY)
    assert notes and "to‘liq emas" in notes[0]


def test_previous_period() -> None:
    assert Period(date(2026, 3, 1), date(2026, 3, 31)).previous() == Period(
        date(2026, 2, 1), date(2026, 2, 28))
    assert Period(date(2026, 7, 1), date(2026, 9, 30)).previous() == Period(
        date(2026, 4, 1), date(2026, 6, 30))
    assert Period(date(2026, 9, 1), date(2026, 9, 27)).previous() == Period(
        date(2026, 8, 1), date(2026, 8, 27))
    assert Period(date(2026, 3, 1), date(2026, 3, 30)).previous() == Period(
        date(2026, 2, 1), date(2026, 2, 28))
    assert Period(date(2026, 8, 10), date(2026, 8, 19)).previous() == Period(
        date(2026, 7, 31), date(2026, 8, 9))


def test_plan_metric_dimension_and_intents() -> None:
    plan = build_plan("O‘tgan oy filiallar savdosini solishtir va dashboard qil", CATALOG)
    assert plan.metric_ids == ["net_sales"] and plan.dimensions == ["branch"]
    assert plan.compare and not plan.explain and plan.dashboard
    assert plan.currency == "UZS"


def test_why_question_triggers_explain() -> None:
    plan = build_plan("Bu oy foyda nega kamaydi?", CATALOG)
    assert plan.metric_ids == ["gross_profit"] and plan.explain and plan.compare
    assert any("yalpi foyda" in n for n in plan.notes)


def test_net_profit_is_not_invented() -> None:
    plan = build_plan("Sof foyda qancha?", CATALOG)
    assert plan.clarification and "Yalpi foyda" in plan.clarification


def test_unknown_metric_asks_one_question() -> None:
    plan = build_plan("Xodimlar kayfiyati qanday?", CATALOG)
    assert plan.clarification and plan.clarification.count("?") == 1


# --- suhbat davomi va metrika nomlari (foydalanuvchi holati: “dashboard qur” → “barchasi”) ---

from ai_runtime.adapters.fake_documents import is_document_request  # noqa: E402
from ai_runtime.adapters.fake_provider import conversation_turns, resolve_followup  # noqa: E402
from ai_runtime.application.commands import RunAgentCommand, initial_items  # noqa: E402

CLARIFY = ("Qaysi ko‘rsatkich kerak? Mavjud metrikalar: Sof savdo tushumi, Chegirmalar, "
           "Qaytarishlar, Hujjatlar soni, Debitorlik qoldig‘i.")
ALL_LIST = ("Sof savdo tushumi, Chegirmalar, Qaytarishlar, Sotilgan mahsulot tannarxi, Yalpi "
            "foyda, Yalpi marja, Hujjatlar soni, Sotilgan miqdor, Debitorlik qoldig‘i, Muddati "
            "o‘tgan debitorlik.")


def turns_of(*pairs: tuple[str, str]) -> list[tuple[str, str]]:
    return list(pairs)


def test_metric_list_answer_is_metrics_not_document_question() -> None:
    tools = {"search_documents", "list_available_metrics"}
    assert not is_document_request(ALL_LIST, tools, has_context=False)
    assert is_document_request("Shartnomada to‘lov muddati necha kun?", tools, has_context=False)
    catalog = {**CATALOG, "metrics": [*CATALOG["metrics"], *(
        {"id": i, "name": i, "unit": "money", "subject": "sales", "dimensions": ["month"]}
        for i in ("order_count", "quantity_sold", "cogs", "gross_margin", "discounts", "returns",
                  "receivables_open", "receivables_overdue") if i not in
        {m["id"] for m in CATALOG["metrics"]})]}
    plan = build_plan(ALL_LIST, catalog)
    assert plan.clarification is None
    assert plan.metric_ids == ["net_sales", "discounts", "returns", "cogs", "gross_profit",
                               "gross_margin"]  # ro‘yxat tartibi, so‘rov chegarasi — 6
    assert any("order_count" in n and "keyingi so‘rovda" in n for n in plan.notes)
    assert any("alohida so‘rov" in n for n in plan.notes)  # debitorlik aralashmaydi
    assert plan.dimensions == []  # “Sotilgan mahsulot tannarxi” — kesim emas


def test_followup_joins_the_original_request() -> None:
    history = turns_of(("user", "menga bir oylik hisobot bo‘yicha dashboard qur"),
                       ("agent", CLARIFY))
    joined = resolve_followup("barchasi", history)
    assert "dashboard" in joined
    plan = build_plan(joined, CATALOG)
    assert plan.clarification is None and plan.dashboard
    assert plan.metric_ids == ["net_sales", "gross_profit"]  # katalogdagi hammasi
    # Ikki marta aniqlashtirilgan zanjir ham boshlang‘ich so‘rovni saqlaydi.
    history += [("user", "barchasi"), ("agent", CLARIFY)]
    joined = resolve_followup("Sof savdo tushumi, Yalpi foyda", history)
    assert joined.startswith("menga bir oylik") and "barchasi" not in joined
    assert build_plan(joined, CATALOG).dashboard
    # Aniqlashtirish bo‘lmagan bo‘lsa, yangi savol o‘zgarmaydi.
    unrelated = [("user", "salom"), ("agent", "Javob")]
    assert resolve_followup("iyun savdosi", unrelated) == "iyun savdosi"


def test_conversation_reaches_the_model_as_developer_context() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    cmd = RunAgentCommand(uuid4(), uuid4(), uuid4(), "finance_analyst", "barchasi", "uz-Latn",
                          datetime.now(UTC), "tok", uuid4(), uuid4(),
                          conversation=({"role": "user", "agent_role_key": None,
                                         "text": "dashboard qur"},
                                        {"role": "agent", "agent_role_key": "finance_analyst",
                                         "text": "Qaysi ko‘rsatkich kerak?\nMavjud: ..."}))
    items = initial_items(cmd)
    assert [i["role"] for i in items] == ["developer", "user"]
    assert items[-1]["content"] == "barchasi"
    assert conversation_turns(items) == [("user", "dashboard qur"),
                                         ("agent", "Qaysi ko‘rsatkich kerak?\nMavjud: ...")]
