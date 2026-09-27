class DomainError(Exception):
    """AgentRun invariantlari buzilganda."""

    code = "DOMAIN_ERROR"


class InvalidTransition(DomainError):
    code = "INVALID_TRANSITION"


class ToolBudgetExceeded(DomainError):
    code = "TOOL_BUDGET_EXCEEDED"


class ToolNotAllowed(DomainError):
    code = "TOOL_NOT_ALLOWED"
