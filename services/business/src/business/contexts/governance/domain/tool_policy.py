"""Tool siyosati (TZ 3, 12, 13.4): agent roli va topshiriq bergan foydalanuvchi roli.

Majburiy tekshiruv shu yerda (Core). AI Runtime’dagi ro‘yxat faqat modelga ko‘rsatish uchun.
Agent vakolati topshiriq bergan foydalanuvchi vakolatidan oshmaydi.
"""

ANALYTICS_READ = frozenset({"list_available_metrics", "run_metric_query", "compare_periods",
                            "explain_contributions"})
ANALYTICS_WRITE = frozenset({"create_dashboard"})

AGENT_TOOLS: dict[str, frozenset[str]] = {
    "coordinator": ANALYTICS_READ | ANALYTICS_WRITE,
    "sales_analyst": ANALYTICS_READ | ANALYTICS_WRITE,
    "finance_analyst": ANALYTICS_READ | ANALYTICS_WRITE,
    "inventory_analyst": ANALYTICS_READ | ANALYTICS_WRITE,
    "document_assistant": frozenset(),  # hujjat vositalari — Bosqich 3
}

# Foydalanuvchi roli → ruxsat etilgan vositalar. Viewer erkin tahlil so‘rovi bera olmaydi.
USER_TOOLS: dict[str, frozenset[str]] = {
    "owner": ANALYTICS_READ | ANALYTICS_WRITE,
    "admin": ANALYTICS_READ | ANALYTICS_WRITE,
    "analyst": ANALYTICS_READ | ANALYTICS_WRITE,
    "viewer": frozenset(),
}

POLICY_VERSION = 1


def tools_for(agent_role: str, user_role: str) -> frozenset[str]:
    return AGENT_TOOLS.get(agent_role, frozenset()) & USER_TOOLS.get(user_role, frozenset())


def is_allowed(tool: str, agent_role: str, user_role: str) -> bool:
    return tool in tools_for(agent_role, user_role)
