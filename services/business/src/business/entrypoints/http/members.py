from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from business.contexts.identity.application.members import InvitationView, MemberView
from business.contexts.identity.domain.model import Role

from .deps import AuthCtx, ContainerDep, Members, PasswordReset, rate_limit
from .identity import SessionResponse
from .security import set_session_cookies

router = APIRouter(prefix="/api/v1", tags=["members"])


class InviteRequest(BaseModel):
    email: str = Field(max_length=254)
    role: Role


class InvitationResponse(BaseModel):
    id: UUID
    email: str
    role: Role
    expires_at: datetime

    @classmethod
    def of(cls, v: InvitationView) -> "InvitationResponse":
        return cls(id=v.id, email=v.email, role=v.role, expires_at=v.expires_at)


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    password: str = Field(max_length=256)


class MemberResponse(BaseModel):
    user_id: UUID
    email: str
    role: Role
    joined_at: datetime

    @classmethod
    def of(cls, v: MemberView) -> "MemberResponse":
        return cls(user_id=v.user_id, email=v.email, role=v.role, joined_at=v.joined_at)


class ChangeRoleRequest(BaseModel):
    role: Role


class PasswordResetRequest(BaseModel):
    email: str = Field(max_length=254)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(max_length=256)


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
async def invite(body: InviteRequest, ctx: AuthCtx, members: Members) -> InvitationResponse:
    return InvitationResponse.of(await members.invite(ctx, body.email, body.role))


@router.get("/invitations")
async def list_invitations(ctx: AuthCtx, members: Members) -> list[InvitationResponse]:
    return [InvitationResponse.of(i) for i in await members.list_invitations(ctx)]


@router.post(
    "/invitations/accept",
    dependencies=[Depends(rate_limit("invite_accept", limit=10, window_seconds=300))],
)
async def accept_invitation(
    body: AcceptInvitationRequest, response: Response, members: Members, container: ContainerDep
) -> SessionResponse:
    issued = await members.accept(body.token, body.password)
    set_session_cookies(response, issued, secure=container.settings.cookie_secure)
    ctx = issued.context
    return SessionResponse(user_id=ctx.user_id, tenant_id=ctx.tenant_id, role=ctx.role,
                           mfa_satisfied=ctx.mfa_satisfied)


@router.get("/members")
async def list_members(ctx: AuthCtx, members: Members) -> list[MemberResponse]:
    return [MemberResponse.of(m) for m in await members.list_members(ctx)]


@router.patch("/members/{user_id}")
async def change_role(
    user_id: UUID, body: ChangeRoleRequest, ctx: AuthCtx, members: Members
) -> MemberResponse:
    return MemberResponse.of(await members.change_role(ctx, user_id, body.role))


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(user_id: UUID, ctx: AuthCtx, members: Members) -> None:
    await members.remove(ctx, user_id)


@router.post(
    "/auth/password-reset",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("password_reset", limit=5, window_seconds=900))],
)
async def request_password_reset(body: PasswordResetRequest, service: PasswordReset) -> None:
    await service.request(body.email)


@router.post(
    "/auth/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("password_reset_confirm", limit=10, window_seconds=900))],
)
async def confirm_password_reset(body: PasswordResetConfirm, service: PasswordReset) -> None:
    await service.confirm(body.token, body.new_password)
