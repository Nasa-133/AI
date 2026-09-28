"""Agent tanlash (TZ 4): aniq tanlov → aniqlashtirishga javob → mutaxassislik → koordinator."""

import pytest

from business.contexts.workspace.domain.tasks import route

METRIC_LIST = ("Sof savdo tushumi, Chegirmalar, Qaytarishlar, Sotilgan mahsulot tannarxi, Yalpi "
               "foyda, Yalpi marja, Hujjatlar soni, Sotilgan miqdor, Debitorlik qoldig‘i")


@pytest.mark.parametrize(("text", "role"), [
    ("Ali, o‘tgan oy savdo", "sales_analyst"),
    ("bu oy yalpi foyda qancha?", "finance_analyst"),
    ("Shartnomada to‘lov muddati necha kun?", "document_assistant"),
    ("menga bir oylik hisobot bo‘yicha dashboard qur", "coordinator"),
    # “Hujjatlar soni” — metrika nomi, fayl haqidagi savol emas.
    ("Hujjatlar soni o‘tgan oy qancha?", "sales_analyst"),
])
def test_specialist_routing(text: str, role: str) -> None:
    assert route(text) == role


def test_answer_to_clarification_returns_to_asking_agent() -> None:
    # Foydalanuvchi holati: koordinator “Qaysi ko‘rsatkich kerak?” deb so‘radi.
    assert route("barchasi", awaiting_role="coordinator") == "coordinator"
    assert route(METRIC_LIST, awaiting_role="coordinator") == "coordinator"
    # Aniq murojaat va tanlangan hujjat ustun turadi.
    assert route("Dilnoza, shartnomani ko‘r", awaiting_role="coordinator") == "document_assistant"
    assert route("savol", awaiting_role="coordinator", has_documents=True) == "document_assistant"
    assert route("barchasi", explicit_role="sales_analyst",
                 awaiting_role="coordinator") == "sales_analyst"
