import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from ai_runtime.adapters.fake_provider import FakeProvider
from ai_runtime.adapters.http_tools import HttpBusinessTools
from ai_runtime.adapters.tool_catalog import load_tool_specs
from ai_runtime.application.runner import AgentRunner
from ai_runtime.domain.run import AgentRun, RunStatus
from ai_runtime.ports.clock import SystemClock
from tests.fake_core import CONTRACTS, SERVICE_TOKEN, FakeCore, validate

from .memory_store import MemoryStore

NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def new_run(text: str, role: str = "sales_analyst", budget: int = 20) -> AgentRun:
    return AgentRun(id=uuid4(), tenant_id=uuid4(), task_id=uuid4(), task_step_id=uuid4(),
                    role_key=role, instruction=text, locale="uz-Latn",
                    deadline=datetime.now(UTC) + timedelta(minutes=10), capability_token="cap",
                    correlation_id=uuid4(), causation_id=uuid4(), max_tool_calls=budget)


def runner(store: MemoryStore, core: FakeCore, owner: str = "w1") -> AgentRunner:
    tools = HttpBusinessTools(base_url="http://core", service_token=SERVICE_TOKEN,
                              client=core.client(), backoff_seconds=0)
    return AgentRunner(store=store, provider=FakeProvider(), tools=tools,
                       tool_specs=load_tool_specs(), clock=SystemClock(), owner=owner,
                       lease=timedelta(seconds=30))


async def run_to_end(text: str, core: FakeCore | None = None, **kw: Any):  # type: ignore[no-untyped-def]
    store, core = MemoryStore(), core or FakeCore()
    run = new_run(text, **kw)
    store.add(run)
    assert await runner(store, core).run_once()
    return store, core, store.runs[run.id]


def completed(store: MemoryStore) -> dict[str, Any]:
    (event,) = [e for e in store.events if e.event_type == "AgentRunCompleted.v1"]
    return event.payload


async def test_full_analytics_flow_emits_contract_valid_events() -> None:
    store, core, run = await run_to_end(
        "Bu oy foyda nega kamaydi? Filiallar bo‘yicha, dashboard qil")
    assert core.names() == ["list_available_metrics", "run_metric_query", "compare_periods",
                            "explain_contributions", "create_dashboard"]
    assert run.status is RunStatus.SUCCEEDED and run.tool_calls_used == 5
    for e in store.events:
        validate(CONTRACTS / "events" / e.event_type.replace(".v1", ".v1.json"), e.payload)
    seqs = [e.aggregate_version for e in store.events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    payload = completed(store)
    answer = payload["result_candidate"]["answer_markdown"]
    assert "hisobiy hissa" in answer and "Gipoteza" in answer and "sabab" not in answer.replace(
        "sababni isbotlamaydi", "")
    assert payload["result_candidate"]["structured"]["dashboard_ids"]
    assert payload["source_refs"] and payload["usage"]["cost_estimate"] == "0"


async def test_answer_numbers_come_only_from_tool_results() -> None:
    store, core, _ = await run_to_end("O‘tgan oy filiallar savdosini solishtir")
    answer = completed(store)["result_candidate"]["answer_markdown"]
    evidence = json.dumps([r for r in core.results.values()], ensure_ascii=False)
    evidence += json.dumps([c[2] for c in core.calls], ensure_ascii=False)
    # UUID va sanalar tool natijasida bor; qolgan har bir son ham shu yerda bo‘lishi kerak.
    text = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27}", "", answer)
    for number in NUMBER.findall(text):
        assert number in evidence, f"{number} tool natijalarida yo‘q"


async def test_clarification_makes_run_partial_without_computation() -> None:
    store, core, run = await run_to_end("Sof foyda qancha?")
    assert core.names() == ["list_available_metrics"]
    assert run.status is RunStatus.PARTIAL
    assert "Aniqlashtiruvchi" in completed(store)["limitations"][0]


async def test_role_without_tools_does_not_call_core() -> None:
    _, core, run = await run_to_end("savdo", role="unknown_role")
    assert core.calls == [] and run.status is RunStatus.PARTIAL


async def test_document_assistant_answers_from_search() -> None:
    store, core, run = await run_to_end("To‘lov muddati qancha?", role="document_assistant")
    assert core.names() == ["search_documents"]
    assert run.status is RunStatus.SUCCEEDED
    result = completed(store)["result_candidate"]
    assert "15 kun" in result["answer_markdown"]
    assert result["kind"] == "answer"


async def test_tool_budget_stops_with_partial() -> None:
    store, _, run = await run_to_end("Bu oy foyda nega kamaydi?", budget=2)
    assert run.status is RunStatus.PARTIAL and run.tool_calls_used == 2
    assert completed(store)["error_code"] == "TOOL_BUDGET_EXCEEDED"


async def test_auth_failure_fails_run() -> None:
    core = FakeCore()
    core.fail_next = [403]
    store, _, run = await run_to_end("savdo", core=core)
    assert run.status is RunStatus.FAILED
    assert completed(store)["error_code"] == "TOOL_AUTH_FAILED"


async def test_cancel_before_next_step() -> None:
    store, core = MemoryStore(), FakeCore()
    run = new_run("savdo")
    run.request_cancel()
    store.add(run)
    await runner(store, core).run_once()
    assert store.runs[run.id].status is RunStatus.CANCELLED and core.calls == []


async def test_resume_after_lost_lease_does_not_repeat_finished_tools() -> None:
    store, core = MemoryStore(), FakeCore()
    run = new_run("O‘tgan oy filiallar savdosini solishtir")
    store.add(run)
    crashing = runner(store, core, owner="w1")
    original = store.commit_step
    commits = 0

    async def crash_after_two_tool_outputs(r, owner, lease, events):  # type: ignore[no-untyped-def]
        nonlocal commits
        await original(r, owner, lease, events)
        commits += 1
        if len(r.checkpoint.tool_outputs()) == 2:
            raise RuntimeError("worker yiqildi")

    store.commit_step = crash_after_two_tool_outputs  # type: ignore[method-assign]
    try:
        await crashing.run_once()
    except RuntimeError:
        pass
    store.commit_step = original  # type: ignore[method-assign]
    store.expire(run.id)
    assert await runner(store, core, owner="w2").run_once()
    assert store.runs[run.id].status is RunStatus.SUCCEEDED
    names = core.names()
    assert names.count("list_available_metrics") == 1 and names.count("run_metric_query") == 1
