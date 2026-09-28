"""Task hayot sikli va agentni tanlash (TZ 4, 11)."""

import re
from enum import StrEnum

from business.kernel.errors import BusinessError

MAX_INSTRUCTION = 20_000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL


TERMINAL = frozenset({TaskStatus.SUCCEEDED, TaskStatus.PARTIAL, TaskStatus.FAILED,
                      TaskStatus.CANCELLED})


class TaskNotCancellable(BusinessError):
    code = "TASK_NOT_CANCELLABLE"


class InvalidMessage(BusinessError):
    code = "VALIDATION_ERROR"


# Standart ismlar (TZ 4). Sozlanadigan AgentProfile — Bosqich 4.
AGENTS: dict[str, tuple[str, str]] = {
    "coordinator": ("Bosh yordamchi", "Koordinator"),
    "sales_analyst": ("Ali", "Savdo analitigi"),
    "finance_analyst": ("Madina", "Moliya analitigi"),
    "inventory_analyst": ("Sardor", "Ombor analitigi"),
    "document_assistant": ("Dilnoza", "Hujjat yordamchisi"),
}
_BY_NAME = {name.lower(): role for role, (name, _) in AGENTS.items()}
_DOCUMENT_RE = re.compile(r"\b(hujjat|shartnoma|band|nizom|kelishuv|reglament)")
_KEYWORDS = (
    ("finance_analyst", ("foyda", "marja", "tannarx", "qarz", "debitor", "xarajat")),
    ("inventory_analyst", ("ombor", "qoldiq", "zaxira")),
    ("sales_analyst", ("savdo", "tushum", "sotuv", "filial", "mijoz", "mahsulot")),
)


def sanitize(text: str) -> str:
    """Boshqaruv belgilari olib tashlanadi; matn ma’nosi o‘zgarmaydi. Uzunlik chegaralanadi."""
    cleaned = _CONTROL.sub("", text).strip()
    if not cleaned:
        raise InvalidMessage("Xabar bo‘sh.")
    if len(cleaned) > MAX_INSTRUCTION:
        raise InvalidMessage(f"Xabar {MAX_INSTRUCTION} belgidan oshmasin.")
    return cleaned


def route(text: str, explicit_role: str | None = None, *, has_documents: bool = False) -> str:
    """Tartib (TZ 4): aniq tanlov (@ism yoki rol) → mutaxassislik → koordinator.

    Hujjat tanlangan (chip) yoki hujjat so‘zlari bo‘lsa — hujjat yordamchisi."""
    if explicit_role is not None:
        if explicit_role not in AGENTS:
            raise InvalidMessage(f"Noma’lum agent: {explicit_role}")
        return explicit_role
    if mention := re.match(r"^\s*@?(\w+)[,:\s]", text + " "):
        if (role := _BY_NAME.get(mention.group(1).lower())) is not None:
            return role
    lowered = text.lower()
    if has_documents or _DOCUMENT_RE.search(lowered):
        return "document_assistant"
    for role, words in _KEYWORDS:
        if any(w in lowered for w in words):
            return role
    return "coordinator"
