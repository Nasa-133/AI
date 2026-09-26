"""Cookie sessiya, CSRF va trace middleware’lari (TZ 3-bo‘lim, 13.12)."""

import hmac
import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from business.contexts.identity.application.dto import IssuedSession

from .errors import error_response

SESSION_COOKIE = "abo_session"
CSRF_COOKIE = "abo_csrf"
CSRF_HEADER = "X-CSRF-Token"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Sessiyasiz boshlanadigan amallar (brauzerda eski cookie qolgan bo‘lishi mumkin).
_CSRF_EXEMPT = {
    "/api/v1/auth/login",
    "/api/v1/tenants",
    "/api/v1/invitations/accept",
    "/api/v1/auth/password-reset",
    "/api/v1/auth/password-reset/confirm",
}
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def set_session_cookies(response: Response, issued: IssuedSession, *, secure: bool) -> None:
    max_age = int((issued.expires_at - datetime.now(UTC)).total_seconds())
    common: dict[str, object] = {"secure": secure, "samesite": "lax", "path": "/",
                                 "max_age": max_age}
    response.set_cookie(SESSION_COOKIE, issued.token, httponly=True, **common)  # type: ignore[arg-type]
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(32), httponly=False, **common)  # type: ignore[arg-type]


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


Handler = Callable[[Request], Awaitable[Response]]


def install_middlewares(app: FastAPI) -> None:
    @app.middleware("http")
    async def csrf(request: Request, call_next: Handler) -> Response:
        if (
            request.method in _UNSAFE_METHODS
            and SESSION_COOKIE in request.cookies
            and request.url.path not in _CSRF_EXEMPT
        ):
            cookie = request.cookies.get(CSRF_COOKIE, "")
            header = request.headers.get(CSRF_HEADER, "")
            if not cookie or not hmac.compare_digest(cookie, header):
                return error_response(request, 403, "CSRF_FAILED",
                                      "CSRF token yo‘q yoki mos emas.")
        return await call_next(request)

    # Oxirgi qo‘shilgan middleware birinchi ishlaydi: trace_id barcha javoblarda bo‘ladi.
    @app.middleware("http")
    async def trace(request: Request, call_next: Handler) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request.state.trace_id = incoming if _TRACE_ID_RE.fullmatch(incoming) else uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.trace_id
        return response
