from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from business.contexts.identity.application.dto import Login, Me, OnboardTenant
from business.contexts.identity.domain.model import Role

from .deps import AuthCtx, ContainerDep, Identity, SessionCtx, rate_limit
from .security import SESSION_COOKIE, clear_session_cookies, set_session_cookies

router = APIRouter(prefix="/api/v1", tags=["identity"])


class OnboardRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    tenant_name: str = Field(max_length=200)
    timezone: str = "Asia/Tashkent"
    base_currency: str = "UZS"


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    tenant_id: UUID | None = None


class SessionResponse(BaseModel):
    user_id: UUID
    tenant_id: UUID
    role: Role
    mfa_satisfied: bool


class MembershipResponse(BaseModel):
    tenant_id: UUID
    tenant_name: str
    role: Role


class MeResponse(BaseModel):
    user_id: UUID
    email: str
    current_tenant_id: UUID
    role: Role
    mfa_enabled: bool
    mfa_satisfied: bool
    memberships: list[MembershipResponse]

    @classmethod
    def of(cls, me: Me) -> "MeResponse":
        return cls(
            user_id=me.user_id,
            email=me.email,
            current_tenant_id=me.current_tenant_id,
            role=me.role,
            mfa_enabled=me.mfa_enabled,
            mfa_satisfied=me.mfa_satisfied,
            memberships=[
                MembershipResponse(tenant_id=m.tenant_id, tenant_name=m.tenant_name, role=m.role)
                for m in me.memberships
            ],
        )


class MfaEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class SwitchTenantRequest(BaseModel):
    tenant_id: UUID


@router.post("/tenants", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("onboard", limit=10, window_seconds=3600))])
async def onboard(
    body: OnboardRequest, response: Response, identity: Identity, container: ContainerDep
) -> SessionResponse:
    issued = await identity.onboard_tenant(OnboardTenant(**body.model_dump()))
    set_session_cookies(response, issued, secure=container.settings.cookie_secure)
    ctx = issued.context
    return SessionResponse(user_id=ctx.user_id, tenant_id=ctx.tenant_id, role=ctx.role,
                           mfa_satisfied=ctx.mfa_satisfied)


@router.post("/auth/login",
             dependencies=[Depends(rate_limit("login", limit=20, window_seconds=300))])
async def login(
    body: LoginRequest, response: Response, identity: Identity, container: ContainerDep
) -> SessionResponse:
    issued = await identity.login(Login(**body.model_dump()))
    set_session_cookies(response, issued, secure=container.settings.cookie_secure)
    ctx = issued.context
    return SessionResponse(user_id=ctx.user_id, tenant_id=ctx.tenant_id, role=ctx.role,
                           mfa_satisfied=ctx.mfa_satisfied)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, identity: Identity) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await identity.logout(token)
    clear_session_cookies(response)


@router.post("/auth/mfa/enroll")
async def mfa_enroll(ctx: SessionCtx, identity: Identity) -> MfaEnrollResponse:
    enrollment = await identity.enroll_mfa(ctx)
    return MfaEnrollResponse(secret=enrollment.secret,
                             provisioning_uri=enrollment.provisioning_uri)


@router.post("/auth/mfa/verify",
             dependencies=[Depends(rate_limit("mfa", limit=10, window_seconds=300))])
async def mfa_verify(body: MfaVerifyRequest, ctx: SessionCtx, identity: Identity) -> MeResponse:
    verified = await identity.verify_mfa(ctx, body.code)
    return MeResponse.of(await identity.get_me(verified))


@router.get("/me")
async def me(ctx: SessionCtx, identity: Identity) -> MeResponse:
    return MeResponse.of(await identity.get_me(ctx))


@router.post("/session/tenant")
async def switch_tenant(
    body: SwitchTenantRequest,
    ctx: AuthCtx,
    response: Response,
    identity: Identity,
    container: ContainerDep,
) -> SessionResponse:
    issued = await identity.switch_tenant(ctx, body.tenant_id)
    set_session_cookies(response, issued, secure=container.settings.cookie_secure)
    new = issued.context
    return SessionResponse(user_id=new.user_id, tenant_id=new.tenant_id, role=new.role,
                           mfa_satisfied=new.mfa_satisfied)
