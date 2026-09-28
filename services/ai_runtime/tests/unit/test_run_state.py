from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from ai_runtime.domain.errors import InvalidTransition, ToolBudgetExceeded, ToolNotAllowed
from ai_runtime.domain.run import AgentRun, Checkpoint, RunStatus

NOW = datetime(2026, 9, 27, 10, tzinfo=UTC)


def make(role: str = "sales_analyst", budget: int = 2) -> AgentRun:
    return AgentRun(id=uuid4(), tenant_id=uuid4(), task_id=uuid4(), task_step_id=uuid4(),
                    role_key=role, instruction="x", locale="uz-Latn",
                    deadline=NOW + timedelta(minutes=10), capability_token="cap",
                    correlation_id=uuid4(), causation_id=uuid4(), max_tool_calls=budget)


def test_happy_path_and_final_is_terminal() -> None:
    run = make()
    run.start()
    run.start()  # lease’dan keyin davom ettirish idempotent
    run.finish(RunStatus.SUCCEEDED)
    with pytest.raises(InvalidTransition):
        run.start()
    with pytest.raises(InvalidTransition):
        run.finish(RunStatus.FAILED)


def test_finish_requires_final_status() -> None:
    run = make()
    run.start()
    with pytest.raises(InvalidTransition):
        run.finish(RunStatus.RUNNING)


def test_cancel_only_before_final() -> None:
    run = make()
    assert run.request_cancel() and run.cancel_requested
    run.start()
    run.finish(RunStatus.CANCELLED)
    done = make()
    done.start()
    done.finish(RunStatus.SUCCEEDED)
    assert done.request_cancel() is False


def test_deadline() -> None:
    run = make()
    assert not run.is_past_deadline(NOW)
    assert run.is_past_deadline(NOW + timedelta(minutes=10))


def test_tool_budget_and_allow_list() -> None:
    run = make(budget=2)
    run.ensure_tool_allowed("run_metric_query")
    with pytest.raises(ToolNotAllowed):
        run.ensure_tool_allowed("send_payment")
    with pytest.raises(ToolNotAllowed):
        make(role="document_assistant").ensure_tool_allowed("run_metric_query")
    run.record_tool_call()
    run.record_tool_call()
    assert not run.has_tool_budget()
    with pytest.raises(ToolBudgetExceeded):
        run.record_tool_call()


def test_checkpoint_pending_calls_and_roundtrip() -> None:
    cp = Checkpoint(items=[
        {"type": "function_call", "call_id": "a", "name": "x", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "a", "output": "{}"},
        {"type": "function_call", "call_id": "b", "name": "y", "arguments": "{}"},
    ])
    assert [c["call_id"] for c in cp.pending_tool_calls()] == ["b"]
    assert Checkpoint.from_json(cp.to_json()) == cp
    assert Checkpoint.from_json(None).items == []


def test_pricing_from_config() -> None:
    from decimal import Decimal

    from ai_runtime.domain.pricing import Pricing

    p = Pricing(Decimal("2.50"), Decimal("10"))
    assert p.cost(1_000_000, 0) == Decimal("2.500000")
    assert p.cost(1200, 300) == Decimal("0.006000")
    assert Pricing().cost(10**9, 10**9) == Decimal("0")
