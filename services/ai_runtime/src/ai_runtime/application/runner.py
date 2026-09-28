"""Agent tool loop (TZ 10 tool loop, 11, 13.9).

Har model/tool qadamidan keyin checkpoint saqlanadi. Worker yiqilsa lease tugaydi va boshqa
worker checkpoint’dan davom etadi: tugallangan tool chaqiruvi takrorlanmaydi, chala qolgan
chaqiruv o‘sha `tool_call_id` bilan qayta yuboriladi (Core deduplikatsiya qiladi).
"""

import json
import logging
from datetime import timedelta
from typing import Any

from ..domain.errors import ToolNotAllowed
from ..domain.pricing import Pricing
from ..domain.roles import allowed_tools
from ..domain.run import AgentRun, RunStatus
from ..ports.clock import Clock
from ..ports.model import ModelProvider, ModelRequest, ModelResponse, ToolSpec
from ..ports.store import LeaseLost, PendingEvent, RunStore
from ..ports.tools import BusinessTools, ToolAuthError, ToolResult, ToolUnavailable
from .prompts import PROMPT_VERSION, instructions_for

logger = logging.getLogger(__name__)

PROGRESSED = "AgentRunProgressed.v1"
COMPLETED = "AgentRunCompleted.v1"

_PHASE_BY_TOOL = {
    "list_available_metrics": "planning",
    "run_metric_query": "computing",
    "compare_periods": "computing",
    "explain_contributions": "analyzing",
    "create_dashboard": "drafting",
    "search_documents": "retrieving",
    "read_document_section": "reading",
    "compare_document_versions": "analyzing",
    "create_document_draft": "drafting",
}
# Aniqlashtiruvchi savol bilan to‘xtagan run: Business agentni “javob kutmoqda” deb ko‘rsatadi.
CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


class _Finished(Exception):
    """Run yakuniy holatga o‘tdi va saqlandi."""


class AgentRunner:
    def __init__(
        self,
        *,
        store: RunStore,
        provider: ModelProvider,
        tools: BusinessTools,
        tool_specs: dict[str, ToolSpec],
        clock: Clock,
        owner: str,
        lease: timedelta,
        pricing: Pricing | None = None,
    ) -> None:
        self._pricing = pricing or Pricing()
        self._store = store
        self._provider = provider
        self._tools = tools
        self._tool_specs = tool_specs
        self._clock = clock
        self._owner = owner
        self._lease = lease

    async def run_once(self) -> bool:
        """Bitta run’ni oladi va oxirigacha (yoki lease yo‘qolguncha) yuritadi."""
        run = await self._store.claim(self._owner, self._lease)
        if run is None:
            return False
        try:
            await self._drive(run)
        except _Finished:
            pass
        except LeaseLost:
            logger.warning("Lease yo‘qoldi, run tashlandi", extra={"agent_run_id": str(run.id)})
        return True

    # --- asosiy sikl -------------------------------------------------------------------
    async def _drive(self, run: AgentRun) -> None:
        if run.status is RunStatus.QUEUED:
            run.start()
            await self._commit(run, self._progress(run, "planning", "Topshiriq qabul qilindi"))
        else:
            run.start()  # lease tugagan run’ni davom ettirish
        if not run.checkpoint.items:
            run.checkpoint.items.append(
                {"type": "message", "role": "user", "content": run.instruction})
            await self._commit(run)

        while True:
            if await self._store.refresh_cancel(run):
                await self._finish(run, RunStatus.CANCELLED, None, ["Foydalanuvchi bekor qildi"])
            if run.is_past_deadline(self._clock.now()):
                await self._finish(run, RunStatus.FAILED, None,
                                   ["Topshiriq muddati tugadi"], error_code="DEADLINE_EXCEEDED")
            pending = run.checkpoint.pending_tool_calls()
            if pending:
                await self._execute_tool(run, pending[0])
                continue
            response = await self._provider.respond(ModelRequest(
                instructions=instructions_for(run.role_key),
                items=run.checkpoint.items,
                tools=[self._tool_specs[n] for n in allowed_tools(run.role_key)
                       if n in self._tool_specs],
            ))
            run.checkpoint.input_tokens += response.input_tokens
            run.checkpoint.output_tokens += response.output_tokens
            if response.status == "refused":
                await self._finish(run, RunStatus.FAILED, None,
                                   ["Model so‘rovni rad etdi"], error_code="MODEL_REFUSED")
            run.checkpoint.items.extend(response.output_items)
            if response.tool_calls:
                await self._commit(run)
                continue
            await self._complete_with_answer(run, response)

    async def _execute_tool(self, run: AgentRun, call: dict[str, Any]) -> None:
        name, call_id = str(call["name"]), str(call["call_id"])
        try:
            run.ensure_tool_allowed(name)
            arguments = json.loads(call.get("arguments") or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("argumentlar obyekt bo‘lishi kerak")
        except (ToolNotAllowed, ValueError) as exc:
            # Model xatosi: natija sifatida qaytariladi, model tuzatishi mumkin.
            await self._append_output(run, call_id, ToolResult(
                status="error", data=None, error_code="INVALID_TOOL_CALL", error_message=str(exc)))
            return
        if not run.has_tool_budget():
            await self._finish_partial_from_evidence(
                run, [f"Tool chaqiruvlari limiti ({run.max_tool_calls}) tugadi"])
        await self._commit(run, self._progress(run, _PHASE_BY_TOOL.get(name, "waiting_tool"),
                                                f"{name} bajarilmoqda"))
        try:
            result = await self._tools.call(tool_name=name, tool_call_id=call_id,
                                            arguments=arguments,
                                            capability=run.capability_token, traceparent=None)
        except ToolAuthError:
            await self._finish(run, RunStatus.FAILED, None,
                               ["Business vositalariga kirish rad etildi"],
                               error_code="TOOL_AUTH_FAILED")
        except ToolUnavailable:
            await self._finish(run, RunStatus.FAILED, None,
                               ["Business vositalari vaqtincha mavjud emas"],
                               error_code="TOOL_UNAVAILABLE")
        run.record_tool_call()
        await self._append_output(run, call_id, result)

    async def _append_output(self, run: AgentRun, call_id: str, result: ToolResult) -> None:
        run.checkpoint.items.append({"type": "function_call_output", "call_id": call_id,
                                     "output": json.dumps(result.to_json(), ensure_ascii=False)})
        await self._commit(run)

    # --- yakunlash ---------------------------------------------------------------------
    async def _complete_with_answer(self, run: AgentRun, response: ModelResponse) -> None:
        limitations = list(response.limitations)
        status = RunStatus.SUCCEEDED
        error_code = None
        if response.needs_clarification:
            status = RunStatus.PARTIAL
            error_code = CLARIFICATION_REQUIRED
            limitations.append("Aniqlashtiruvchi savolga javob kerak")
        if response.status == "incomplete":
            status = RunStatus.PARTIAL
            limitations.append("Model javobi to‘liq emas")
        await self._commit(run, self._progress(run, "drafting", "Javob tayyorlanmoqda"))
        await self._finish(run, status, response.text, limitations, error_code=error_code)

    async def _finish_partial_from_evidence(self, run: AgentRun, limitations: list[str]) -> None:
        await self._finish(run, RunStatus.PARTIAL,
                           "Topshiriq limit sababli to‘liq bajarilmadi; yig‘ilgan natijalar "
                           "manbalarda.", limitations, error_code="TOOL_BUDGET_EXCEEDED")

    async def _finish(self, run: AgentRun, status: RunStatus, answer: str | None,
                      limitations: list[str], *, error_code: str | None = None) -> None:
        outputs = [ToolResult.from_json(json.loads(o))
                   for o in run.checkpoint.tool_outputs().values()]
        warnings = [w for r in outputs for w in r.warnings]
        run.finish(status)
        payload: dict[str, Any] = {
            "task_id": str(run.task_id),
            "task_step_id": str(run.task_step_id),
            "agent_run_id": str(run.id),
            "status": status.value,
            "result_candidate": None if answer is None else {
                "kind": "document_patch" if any(
                    r.status == "ok" and "draft_version_id" in (r.data or {}) for r in outputs)
                else "answer", "answer_markdown": answer,
                "structured": _structured(run, outputs)},
            "source_refs": _source_refs(outputs),
            "limitations": [x[:500] for x in dict.fromkeys(limitations + warnings)],
            "error_code": error_code,
            "usage": {"input_tokens": run.checkpoint.input_tokens,
                      "output_tokens": run.checkpoint.output_tokens,
                      # Narx konfiguratsiyadan (TZ 19); limit va hisob Governance’da.
                      "cost_estimate": str(self._pricing.cost(run.checkpoint.input_tokens,
                                                              run.checkpoint.output_tokens)),
                      "currency": self._pricing.currency},
        }
        await self._commit(run, PendingEvent(COMPLETED, payload, run.next_sequence()))
        raise _Finished

    # --- yordamchilar ------------------------------------------------------------------
    def _progress(self, run: AgentRun, phase: str, message: str) -> PendingEvent:
        seq = run.next_sequence()
        return PendingEvent(PROGRESSED, {
            "task_id": str(run.task_id), "task_step_id": str(run.task_step_id),
            "agent_run_id": str(run.id), "phase": phase, "message": message,
            "tool_calls_used": run.tool_calls_used, "sequence": seq,
        }, seq)

    async def _commit(self, run: AgentRun, *events: PendingEvent) -> None:
        await self._store.commit_step(run, self._owner, self._lease, list(events))


def _source_refs(outputs: list[ToolResult]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for result in outputs:
        if result.status != "ok":
            continue
        for ref in result.source_refs:
            seen.setdefault((str(ref["kind"]), str(ref["id"])), ref)
    return list(seen.values())


def _structured(run: AgentRun, outputs: list[ToolResult]) -> dict[str, Any]:
    query_ids: list[str] = []
    dashboards: list[str] = []
    drafts: list[dict[str, str]] = []
    for result in outputs:
        data = result.data or {}
        if result.status == "ok" and "draft_version_id" in data:
            drafts.append({"document_id": str(data["document_id"]),
                           "version_id": str(data["draft_version_id"])})
        if "query_spec_id" in data:
            query_ids.append(str(data["query_spec_id"]))
        if "dashboard_id" in data:
            dashboards.append(str(data["dashboard_id"]))
    return {"prompt_version": PROMPT_VERSION, "role_key": run.role_key,
            "query_spec_ids": list(dict.fromkeys(query_ids)),
            "dashboard_ids": list(dict.fromkeys(dashboards)),
            "document_drafts": drafts,
            "tool_calls_used": run.tool_calls_used}
