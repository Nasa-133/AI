from typing import Annotated

from fastapi import Depends, Request

from business.bootstrap.container import Container
from business.contexts.identity.application.dto import AuthContext
from business.contexts.identity.application.errors import MfaRequired, Unauthenticated
from business.contexts.identity.application.service import IdentityService

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
    return await identity.authenticate(token)


async def auth_context(ctx: Annotated[AuthContext, Depends(session_context)]) -> AuthContext:
    """Barcha biznes endpointlari uchun: MFA talabi bajarilgan bo‘lishi shart."""
    if not ctx.mfa_satisfied:
        raise MfaRequired("Davom etish uchun ikki bosqichli tasdiqlashni yakunlang.")
    return ctx


ContainerDep = Annotated[Container, Depends(get_container)]
SessionCtx = Annotated[AuthContext, Depends(session_context)]
AuthCtx = Annotated[AuthContext, Depends(auth_context)]
Identity = Annotated[IdentityService, Depends(get_identity)]
