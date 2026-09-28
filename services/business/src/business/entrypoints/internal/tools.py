"""Tool API (TZ 12, 13.9 qadam 4): AI Runtime → Core. Brauzerga ochilmaydi (Edge’da yopiq).

Har chaqiriqda: servis tokeni → capability imzosi/muddati → joriy a’zolik va rol (DB) →
tool siyosati → argument schema → idempotentlik → bajarish. Biznes xatosi HTTP 200 + status=error.
"""

import hmac
import json
from datetime import UTC, datetime
from importlib import resources
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, Field

from business.bootstrap.container import Container
from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.contexts.analytics.application.comparisons import ComparisonService
from business.contexts.analytics.application.queries import QueryContext, QueryService
from business.contexts.dashboards.adapters.sql import AnalyticsQueryResults, SqlDashboardStore
from business.contexts.dashboards.application.service import DashboardService
from business.contexts.documents.application.common import Viewer as DocViewer
from business.contexts.documents.domain.patch import ReplaceText
from business.contexts.governance.public import SqlAuditLog, is_allowed
from business.contexts.workspace.adapters.tool_calls import SqlToolCallLog
from business.kernel.errors import BusinessError
from business.platform.capability import Capability, InvalidCapability
from business.platform.db import tenant_transaction

from ..http.deps import ContainerDep
from ..wiring import document_services, task_privacy

DOCUMENT_TOOLS = frozenset({"search_documents", "read_document_section",
                            "compare_document_versions", "create_document_draft"})

router = APIRouter(prefix="/internal/v1/tools", tags=["internal-tools"], include_in_schema=False)


def _load_validators() -> dict[str, Draft202012Validator]:
    out = {}
    for f in resources.files(__package__).joinpath("tool_schemas").iterdir():
        if f.name.endswith(".args.v1.json"):
            out[f.name.removesuffix(".args.v1.json")] = Draft202012Validator(
                json.loads(f.read_text("utf-8")), format_checker=FormatChecker())
    return out


VALIDATORS = _load_validators()


class ToolRequest(BaseModel):
    tool_call_id: str = Field(min_length=1, max_length=200)
    arguments: dict[str, Any]


def _result(trace_id: str, *, data: dict[str, Any] | None = None,
            refs: list[dict[str, Any]] | None = None, warnings: list[str] | None = None,
            error: BusinessError | None = None) -> dict[str, Any]:
    return {"status": "error" if error else "ok", "data": data, "source_refs": refs or [],
            "warnings": warnings or [], "error_code": error.code if error else None,
            "error_message": error.message if error else None, "trace_id": trace_id}


def _deny(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "code": code, "message": message, "retryable": False,
        "trace_id": request.state.trace_id})


class ToolArgumentsInvalid(BusinessError):
    code = "INVALID_ARGUMENTS"


def _doc_refs(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hujjat manbalari: aniq versiya va manzil (TZ 9.3, D01)."""
    return [{"kind": "document_version", "id": r["document_id"], "version_id": r["version_id"],
             "locator": r["locator"]} for r in results]


AUDITED_TOOLS = {"create_dashboard": "agent.dashboard_created",
                 "create_document_draft": "agent.document_draft_created"}


async def _execute_documents(conn: Any, container: Container, cap: Capability, role: str,
                             name: str, args: dict[str, Any],
                             ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    services = document_services(container, conn, cap.tenant_id)
    viewer = DocViewer(cap.user_id, role)
    match name:
        case "search_documents":
            ids = [UUID(i) for i in args["document_ids"]] if args["document_ids"] else None
            data = await services.reading.search(viewer, args["query"], ids,
                                                 args["limit"] or 8)
            return data, _doc_refs(data["results"])
        case "read_document_section":
            data = await services.reading.read_section(
                viewer, UUID(args["document_id"]), UUID(args["version_id"]), args["section_id"])
            return data, _doc_refs([data])
        case "compare_document_versions":
            data = await services.reading.compare(viewer, UUID(args["document_id"]),
                                                  UUID(args["left_version_id"]),
                                                  UUID(args["right_version_id"]))
            return data, []
        case "create_document_draft":
            data = await services.editing.create_draft(
                viewer, UUID(args["document_id"]), UUID(args["base_version_id"]),
                UUID(args["expected_version_id"]),
                [ReplaceText(o["section_id"], o["find"], o["replace"], o["occurrence"])
                 for o in args["operations"]], args["comment"])
            return data, [{"kind": "document_version", "id": data["document_id"],
                           "version_id": data["draft_version_id"], "locator": None}]
    raise ToolArgumentsInvalid(f"Noma’lum vosita: {name}")


async def _execute(conn: Any, cap: Capability, name: str, args: dict[str, Any],
                   ctx: QueryContext) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    store = SqlAnalyticsStore(conn, cap.tenant_id)
    queries = QueryService(store)
    match name:
        case "list_available_metrics":
            return await queries.list_metrics(ctx, args["subject"]), []
        case "run_metric_query":
            return await queries.run(ctx, args)
        case "compare_periods":
            return await ComparisonService(queries).compare(ctx, args)
        case "explain_contributions":
            return await ComparisonService(queries).explain(ctx, args)
        case "create_dashboard":
            service = DashboardService(SqlDashboardStore(conn, cap.tenant_id),
                                       AnalyticsQueryResults(store))
            d = await service.create(user_id=cap.user_id, task_id=cap.task_id,
                                     title=args["title"], description=args["description"],
                                     widgets=args["widgets"])
            return {"dashboard_id": str(d.id), "version": d.version, "title": d.spec["title"],
                    "widget_count": len(d.spec["widgets"])}, []
    raise ToolArgumentsInvalid(f"Noma’lum vosita: {name}")


@router.post("/{name}")
async def call_tool(name: str, body: ToolRequest, request: Request, container: ContainerDep,
                    authorization: str = Header(default=""),
                    x_abo_capability: str = Header(default="")) -> Any:
    settings, trace_id = container.settings, request.state.trace_id
    expected = f"Bearer {settings.tools_service_token}"
    if not hmac.compare_digest(authorization.encode(), expected.encode()):
        return _deny(request, 401, "UNAUTHENTICATED", "Servis tokeni noto‘g‘ri.")
    now = datetime.now(UTC)
    try:
        cap = container.capabilities.verify(x_abo_capability, now)
    except InvalidCapability as exc:
        return _deny(request, 403, exc.code, exc.message)
    # Delegation authoritative tekshiruvi: a’zolik bekor qilingan bo‘lsa to‘xtaydi (TZ 13.12).
    role = await container.identity.role_of(cap.tenant_id, cap.user_id)
    if role is None or name not in cap.tools or not is_allowed(name, cap.role_key, role.value):
        return _deny(request, 403, "FORBIDDEN", "Bu vosita uchun vakolat yo‘q.")
    if name not in VALIDATORS:
        return _result(trace_id, error=ToolArgumentsInvalid(f"Noma’lum vosita: {name}"))
    errors = sorted(VALIDATORS[name].iter_errors(body.arguments), key=lambda e: e.path)
    if errors:
        return _result(trace_id, error=ToolArgumentsInvalid(
            "; ".join(f"{'/'.join(map(str, e.path)) or '(ildiz)'}: {e.message}"
                      for e in errors[:5])))

    profile = await container.identity.tenant_profile(cap.tenant_id)
    ctx = QueryContext(cap.user_id, cap.task_id, now.astimezone(ZoneInfo(profile.timezone)).date(),
                       profile.timezone)
    async with tenant_transaction(container.engine, tenant_id=cap.tenant_id,
                                  user_id=cap.user_id) as conn:
        log = SqlToolCallLog(conn, cap.tenant_id)
        if (cached := await log.get(cap.task_id, body.tool_call_id)) is not None:
            return cached
        # TZ 13.12: model ko‘rgan tokenlar → asl qiymat (bajarish uchun); natija → tokenlar.
        privacy = await task_privacy(container, conn, cap.tenant_id, cap.task_id)
        arguments = await privacy.unmask_data(body.arguments)
        try:
            async with conn.begin_nested():
                if name in DOCUMENT_TOOLS:
                    data, refs = await _execute_documents(conn, container, cap, role.value, name,
                                                          arguments)
                else:
                    data, refs = await _execute(conn, cap, name, arguments, ctx)
            data = await privacy.mask_data(data)
            warnings = [*data.get("notes", []), *data.get("warnings", [])]
            result = _result(trace_id, data=data, refs=refs, warnings=warnings)
        except BusinessError as exc:
            result = _result(trace_id, error=exc)
        await log.save(cap.task_id, body.tool_call_id, name, result)
        if name in AUDITED_TOOLS and result["status"] == "ok":
            # Agent yaratgan artifact — audit’da (foydalanuvchi nomidan, agent orqali).
            data = result["data"] or {}
            await SqlAuditLog(conn, cap.tenant_id).record(
                actor_id=cap.user_id, actor_kind="agent", action=AUDITED_TOOLS[name],
                target_type="task", target_id=str(cap.task_id),
                details={"role": cap.role_key, "tool_call_id": body.tool_call_id,
                         **{k: str(data[k]) for k in ("dashboard_id", "document_id",
                                                      "draft_version_id") if k in data}},
                ip=None)
    return result


