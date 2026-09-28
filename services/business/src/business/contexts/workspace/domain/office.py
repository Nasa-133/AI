"""Agentning vizual holati task/step holatidan hosil qilinadi (TZ 6 “Holatlar”, 11).

Hech qanday “ishlayapti” holati o‘ylab topilmaydi: faqat backend’dagi step va task holati.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class AgentState(StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    READING = "reading"
    ANALYZING = "analyzing"
    DRAFTING = "drafting"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Bir nechta faol step bo‘lsa eng “yuqori” holat ko‘rsatiladi (TZ 6).
PRIORITY: tuple[AgentState, ...] = (
    AgentState.AWAITING_APPROVAL, AgentState.AWAITING_INPUT, AgentState.FAILED,
    AgentState.DRAFTING, AgentState.ANALYZING, AgentState.READING, AgentState.QUEUED,
)
KIND_STATE = {
    "read": AgentState.READING, "retrieve": AgentState.READING,
    "compute": AgentState.ANALYZING, "analyze": AgentState.ANALYZING,
    "draft": AgentState.DRAFTING, "dashboard": AgentState.DRAFTING, "export": AgentState.DRAFTING,
}
# AI Runtime bosqichi (AgentRunProgressed.phase) → step turi (TZ 11).
PHASE_KIND = {
    "reading": "read", "retrieving": "retrieve", "computing": "compute", "analyzing": "analyze",
    "planning": "analyze", "waiting_tool": "analyze", "drafting": "draft",
}
IDLE_AFTER = timedelta(seconds=30)
INPUT_WAIT_MAX = timedelta(hours=1)
CLARIFICATION = "CLARIFICATION_REQUIRED"
TERMINAL_TASK = frozenset({"succeeded", "partial", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class AgentTask:
    """Agentga bog‘langan vazifa va uning (P0 da yagona) qadami."""

    task_id: str
    status: str  # task holati
    step_status: str  # pending/running/waiting/…
    step_kind: str
    wait_reason: str | None
    error_code: str | None
    updated_at: datetime
    answered: bool = False  # suhbatda keyingi xabar bor (aniqlashtirishga javob berilgan)
    dispatched: bool = True  # False — agent navbatida, AI’ga hali yuborilmagan


def task_state(t: AgentTask, now: datetime) -> AgentState | None:
    """None — bu vazifa agent holatiga endi ta’sir qilmaydi."""
    if t.status in TERMINAL_TASK:
        if (t.status == "partial" and t.error_code == CLARIFICATION and not t.answered
                and now - t.updated_at < INPUT_WAIT_MAX):
            return AgentState.AWAITING_INPUT
        if now - t.updated_at >= IDLE_AFTER:
            return None
        return {"succeeded": AgentState.COMPLETED, "partial": AgentState.COMPLETED,
                "failed": AgentState.FAILED, "cancelled": AgentState.CANCELLED}[t.status]
    if t.step_status == "failed":
        return AgentState.FAILED
    if t.step_status == "waiting":
        return (AgentState.AWAITING_APPROVAL if t.wait_reason == "approval"
                else AgentState.AWAITING_INPUT)
    if t.step_status == "running":
        return KIND_STATE.get(t.step_kind, AgentState.ANALYZING)
    return AgentState.QUEUED


def agent_state(tasks: list[AgentTask], now: datetime) -> tuple[AgentState, AgentTask | None]:
    """(holat, shu holatni bergan vazifa). Faol holatlar yakuniy holatlardan ustun."""
    active: list[tuple[AgentState, AgentTask]] = []
    finished: list[tuple[AgentState, AgentTask]] = []
    for t in tasks:
        state = task_state(t, now)
        if state is None:
            continue
        is_final = state in (AgentState.COMPLETED, AgentState.CANCELLED) or (
            state is AgentState.FAILED and t.status in TERMINAL_TASK)
        (finished if is_final else active).append((state, t))
    if active:
        # Teng holatda: AI’ga yuborilgani, keyin eng uzoq davom etayotgani (navbat tartibi).
        return min(active, key=lambda p: (PRIORITY.index(p[0]), not p[1].dispatched,
                                          p[1].updated_at))
    if finished:
        return max(finished, key=lambda p: p[1].updated_at)
    return AgentState.IDLE, None
