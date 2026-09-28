from datetime import UTC, datetime, timedelta

import pytest

from business.contexts.workspace.domain.office import AgentState, AgentTask, agent_state, task_state

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def t(status: str = "running", step: str = "running", kind: str = "analyze", *,
      reason: str | None = None, error: str | None = None, ago: int = 0,
      answered: bool = False, tid: str = "t") -> AgentTask:
    return AgentTask(tid, status, step, kind, reason, error, NOW - timedelta(seconds=ago), answered)


@pytest.mark.parametrize(("task", "state"), [
    (t("queued", "pending"), AgentState.QUEUED),
    (t(kind="read"), AgentState.READING),
    (t(kind="retrieve"), AgentState.READING),
    (t(kind="compute"), AgentState.ANALYZING),
    (t(kind="dashboard"), AgentState.DRAFTING),
    (t(step="waiting", reason="input"), AgentState.AWAITING_INPUT),
    (t(step="waiting", reason="approval"), AgentState.AWAITING_APPROVAL),
    (t("succeeded", "succeeded", ago=5), AgentState.COMPLETED),
    (t("partial", "succeeded", ago=5), AgentState.COMPLETED),
    (t("failed", "failed", ago=5), AgentState.FAILED),
    (t("cancelled", "cancelled", ago=5), AgentState.CANCELLED),
])
def test_mapping_table(task: AgentTask, state: AgentState) -> None:  # TZ 6 jadvali
    assert task_state(task, NOW) is state


def test_terminal_returns_to_idle_after_30_seconds() -> None:
    assert agent_state([t("succeeded", "succeeded", ago=31)], NOW) == (AgentState.IDLE, None)
    assert agent_state([], NOW) == (AgentState.IDLE, None)


def test_clarification_waits_for_answer() -> None:
    asked = t("partial", "succeeded", error="CLARIFICATION_REQUIRED", ago=600)
    assert task_state(asked, NOW) is AgentState.AWAITING_INPUT
    answered = t("partial", "succeeded", error="CLARIFICATION_REQUIRED", ago=600, answered=True)
    assert task_state(answered, NOW) is None


def test_priority_and_active_over_finished() -> None:
    state, task = agent_state([
        t(kind="read", tid="a"), t(kind="draft", tid="b"), t("queued", "pending", tid="c"),
        t("succeeded", "succeeded", ago=1, tid="d")], NOW)
    assert (state, task and task.task_id) == (AgentState.DRAFTING, "b")
    state, _ = agent_state([t(kind="draft"), t(step="waiting", reason="input")], NOW)
    assert state is AgentState.AWAITING_INPUT


def test_queued_tie_prefers_dispatched_then_oldest() -> None:
    waiting = AgentTask("w", "queued", "pending", "analyze", None, None, NOW, dispatched=False)
    old = t("queued", "pending", ago=20, tid="old")
    new = t("queued", "pending", ago=1, tid="new")
    _, task = agent_state([waiting, new, old], NOW)
    assert task is not None and task.task_id == "old"
