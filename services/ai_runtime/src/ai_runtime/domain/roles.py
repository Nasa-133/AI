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

KNOWN_TOOLS: frozenset[str] = frozenset(ANALYTICS_TOOLS)

ROLE_TOOLS: dict[str, tuple[str, ...]] = {
    "coordinator": ANALYTICS_TOOLS,
    "sales_analyst": ANALYTICS_TOOLS,
    "finance_analyst": ANALYTICS_TOOLS,
    "inventory_analyst": ANALYTICS_TOOLS,
    # Hujjat vositalari Bosqich 3 da qo‘shiladi.
    "document_assistant": (),
}


def allowed_tools(role_key: str) -> tuple[str, ...]:
    return ROLE_TOOLS.get(role_key, ())
