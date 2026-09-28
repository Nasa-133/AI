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
# Metrika nomlari: “Hujjatlar soni” — savdo ko‘rsatkichi, fayl haqidagi savol emas.
_METRIC_NAMES_RE = re.compile(r"\bhujjat(lar)? soni")
_KEYWORDS = (
    ("finance_analyst", ("foyda", "marja", "tannarx", "qarz", "debitor", "xarajat")),
    ("inventory_analyst", ("ombor", "qoldiq", "zaxira")),
    ("sales_analyst", ("savdo", "tushum", "sotuv", "filial", "mijoz", "mahsulot", "chegirma",
                       "qaytarish", "hujjatlar soni", "sotilgan miqdor", "bitim", "sdelka",
                       "voronka", "konversiya", "lid", "crm")),
)


def sanitize(text: str) -> str:
    """Boshqaruv belgilari olib tashlanadi; matn ma’nosi o‘zgarmaydi. Uzunlik chegaralanadi."""
    cleaned = _CONTROL.sub("", text).strip()
    if not cleaned:
        raise InvalidMessage("Xabar bo‘sh.")
    if len(cleaned) > MAX_INSTRUCTION:
        raise InvalidMessage(f"Xabar {MAX_INSTRUCTION} belgidan oshmasin.")
    return cleaned


def route(text: str, explicit_role: str | None = None, *, has_documents: bool = False,
          awaiting_role: str | None = None) -> str:
    """Tartib (TZ 4): aniq tanlov (@ism yoki rol) → aniqlashtirishga javob → mutaxassislik →
    koordinator.

    `awaiting_role` — shu suhbatda aniqlashtiruvchi savol bergan va javob kutayotgan agent:
    “barchasi”, “ha, filiallar bo‘yicha” kabi javob o‘sha agentga qaytadi.
    Hujjat tanlangan (chip) yoki hujjat so‘zlari bo‘lsa — hujjat yordamchisi."""
    if explicit_role is not None:
        if explicit_role not in AGENTS:
            raise InvalidMessage(f"Noma’lum agent: {explicit_role}")
        return explicit_role
    if mention := re.match(r"^\s*@?(\w+)[,:\s]", text + " "):
        if (role := _BY_NAME.get(mention.group(1).lower())) is not None:
            return role
    if awaiting_role in AGENTS and not has_documents:
        return str(awaiting_role)
    lowered = text.lower()
    if has_documents or _DOCUMENT_RE.search(_METRIC_NAMES_RE.sub(" ", lowered)):
        return "document_assistant"
    for role, words in _KEYWORDS:
        if any(w in lowered for w in words):
            return role
    return "coordinator"
