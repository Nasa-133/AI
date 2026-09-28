"""Rol → modelga ko‘rsatiladigan vositalar.

Bu ruxsat manbai emas: majburiy tekshiruv Core Tool API’da (TZ 13.4, Governance).
AI tomonda faqat ro‘yxatda yo‘q vosita chaqirilmasligi kafolatlanadi.
"""

ANALYTICS_TOOLS: tuple[str, ...] = (
    "list_available_metrics",
    "run_metric_query",
    "compare_periods",
    "explain_contributions",
    "create_dashboard",
)
DOCUMENT_READ_TOOLS: tuple[str, ...] = (
    "search_documents",
    "read_document_section",
    "compare_document_versions",
)
DOCUMENT_TOOLS: tuple[str, ...] = (*DOCUMENT_READ_TOOLS, "create_document_draft")

KNOWN_TOOLS: frozenset[str] = frozenset(ANALYTICS_TOOLS + DOCUMENT_TOOLS)

ROLE_TOOLS: dict[str, tuple[str, ...]] = {
    # Koordinator hujjatni o‘qiy oladi; tahrir — hujjat yordamchisi orqali.
    "coordinator": ANALYTICS_TOOLS + DOCUMENT_READ_TOOLS,
    "sales_analyst": ANALYTICS_TOOLS,
    "finance_analyst": ANALYTICS_TOOLS + DOCUMENT_READ_TOOLS,
    "inventory_analyst": ANALYTICS_TOOLS,
    "document_assistant": DOCUMENT_TOOLS,
}


def allowed_tools(role_key: str) -> tuple[str, ...]:
    return ROLE_TOOLS.get(role_key, ())
