"""Xatolarni standart formatga aylantirish (TZ 15): {code, message, retryable, trace_id}."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from business.kernel.errors import BusinessError

logger = logging.getLogger(__name__)

_STATUS_BY_CODE = {
    "VALIDATION_ERROR": 422,
    "INVALID_CREDENTIALS": 401,
    "UNAUTHENTICATED": 401,
    "MFA_REQUIRED": 403,
    "CSRF_FAILED": 403,
    "FORBIDDEN": 403,
    "BRANCH_FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "EMAIL_TAKEN": 409,
    "MFA_ALREADY_ENABLED": 409,
    "MFA_NOT_ENROLLED": 409,
    "VERSION_CONFLICT": 409,
    "INVALID_MFA_CODE": 422,
    "ACCOUNT_LOCKED": 429,
    "RATE_LIMITED": 429,
    "LAST_OWNER": 409,
    "ALREADY_MEMBER": 409,
    "ALREADY_CONNECTED": 409,
    "INVITATION_INVALID": 410,
    "RESET_TOKEN_INVALID": 410,
    "TASK_NOT_CANCELLABLE": 409,
    "INVALID_DASHBOARD": 422,
    "NO_DATA": 404,
    "METRIC_SETTINGS_NOT_APPROVED": 409,
    "UNSUPPORTED_MEDIA_TYPE": 415,
    "PAYLOAD_TOO_LARGE": 413,
    "SOURCE_NOT_READY": 409,
    "UNKNOWN_METRIC": 422,
    "UNSUPPORTED_DIMENSION": 422,
    "INVALID_QUERY": 422,
    "PATCH_TARGET_INVALID": 422,
    "DOCUMENT_NOT_READY": 409,
    "DOCUMENT_UNREADABLE": 415,
}


def error_response(
    request: Request, status: int, code: str, message: str, *, retryable: bool = False
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "retryable": retryable,
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def _business(request: Request, exc: BusinessError) -> JSONResponse:
        status = _STATUS_BY_CODE.get(exc.code, 400)
        return error_response(request, status, exc.code, exc.message, retryable=exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) for e in exc.errors())
        return error_response(
            request, 422, "VALIDATION_ERROR", f"So‘rov maydonlari noto‘g‘ri: {fields}"
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Kutilmagan xato", extra={"trace_id": request.state.trace_id})
        return error_response(
            request,
            500,
            "INTERNAL",
            "Ichki xato. trace_id bilan qo‘llab-quvvatlashga murojaat qiling.",
            retryable=True,
        )
