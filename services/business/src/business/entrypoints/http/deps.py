from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from business.bootstrap.container import Container
from business.contexts.identity.application.dto import AuthContext
from business.contexts.identity.application.errors import MfaRequired, Unauthenticated
from business.contexts.identity.application.members import MembershipService
from business.contexts.identity.application.password_reset import PasswordResetService
from business.contexts.identity.application.service import IdentityService
from business.kernel.errors import BusinessError

from .security import SESSION_COOKIE


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def get_identity(container: Annotated[Container, Depends(get_container)]) -> IdentityService:
    return container.identity


async def session_context(
    request: Request, identity: Annotated[IdentityService, Depends(get_identity)]
) -> AuthContext:
    """Sessiya bor, lekin MFA hali tasdiqlanmagan bo‘lishi mumkin (faqat /me va /auth/mfa/*)."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise Unauthenticated("Tizimga kiring.")
    ctx = await identity.authenticate(token)
    request.state.audit_actor = (ctx.tenant_id, ctx.user_id)  # audit middleware uchun
    return ctx


async def auth_context(ctx: Annotated[AuthContext, Depends(session_context)]) -> AuthContext:
    """Barcha biznes endpointlari uchun: MFA talabi bajarilgan bo‘lishi shart."""
    if not ctx.mfa_satisfied:
        raise MfaRequired("Davom etish uchun ikki bosqichli tasdiqlashni yakunlang.")
    return ctx


ContainerDep = Annotated[Container, Depends(get_container)]
SessionCtx = Annotated[AuthContext, Depends(session_context)]
AuthCtx = Annotated[AuthContext, Depends(auth_context)]
Identity = Annotated[IdentityService, Depends(get_identity)]


class RateLimited(BusinessError):
    code = "RATE_LIMITED"
    retryable = True


def rate_limit(scope: str, *, limit: int, window_seconds: int) -> Callable[..., Awaitable[None]]:
    """IP bo‘yicha fixed-window limit (login, parol tiklash, MFA, taklifni qabul qilish)."""

    async def dependency(request: Request,
                         container: Annotated[Container, Depends(get_container)]) -> None:
        client = request.client.host if request.client else "unknown"
        allowed = await container.rate_limiter.hit(f"{scope}:ip:{client}", limit=limit,
                                                   window_seconds=window_seconds)
        if not allowed:
            raise RateLimited("Juda ko‘p urinish. Birozdan keyin qayta urinib ko‘ring.")

    return dependency


def get_members(container: Annotated[Container, Depends(get_container)]) -> MembershipService:
    return container.members


def get_password_reset(
    container: Annotated[Container, Depends(get_container)],
) -> PasswordResetService:
    return container.password_reset


Members = Annotated[MembershipService, Depends(get_members)]
PasswordReset = Annotated[PasswordResetService, Depends(get_password_reset)]
