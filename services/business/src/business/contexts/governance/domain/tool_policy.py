"""Tool siyosati (TZ 3, 12, 13.4): agent roli va topshiriq bergan foydalanuvchi roli.

Majburiy tekshiruv shu yerda (Core). AI Runtime’dagi ro‘yxat faqat modelga ko‘rsatish uchun.
Agent vakolati topshiriq bergan foydalanuvchi vakolatidan oshmaydi.
"""

ANALYTICS_READ = frozenset({"list_available_metrics", "run_metric_query", "compare_periods",
                            "explain_contributions"})
ANALYTICS_WRITE = frozenset({"create_dashboard"})
DOCUMENTS_READ = frozenset({"search_documents", "read_document_section",
                            "compare_document_versions"})
DOCUMENTS_WRITE = frozenset({"create_document_draft"})

AGENT_TOOLS: dict[str, frozenset[str]] = {
    "coordinator": ANALYTICS_READ | ANALYTICS_WRITE | DOCUMENTS_READ,
    "sales_analyst": ANALYTICS_READ | ANALYTICS_WRITE,
    "finance_analyst": ANALYTICS_READ | ANALYTICS_WRITE | DOCUMENTS_READ,
    "inventory_analyst": ANALYTICS_READ | ANALYTICS_WRITE,
    "document_assistant": DOCUMENTS_READ | DOCUMENTS_WRITE,
}

# Foydalanuvchi roli → ruxsat etilgan vositalar. Viewer erkin tahlil so‘rovi bera olmaydi,
# lekin o‘ziga ulashilgan hujjatlarni o‘qiy oladi (qidiruvda ACL baribir qo‘llanadi).
ALL = ANALYTICS_READ | ANALYTICS_WRITE | DOCUMENTS_READ | DOCUMENTS_WRITE
USER_TOOLS: dict[str, frozenset[str]] = {
    "owner": ALL,
    "admin": ALL,
    "analyst": ALL,
    "viewer": DOCUMENTS_READ,
}

POLICY_VERSION = 1


def tools_for(agent_role: str, user_role: str) -> frozenset[str]:
    return AGENT_TOOLS.get(agent_role, frozenset()) & USER_TOOLS.get(user_role, frozenset())


def is_allowed(tool: str, agent_role: str, user_role: str) -> bool:
    return tool in tools_for(agent_role, user_role)
