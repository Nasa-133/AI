from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from business.contexts.identity.application.dto import AuthContext, Login, OnboardTenant
from business.contexts.identity.application.errors import InvalidCredentials, NotAMember
from business.contexts.identity.application.members import AlreadyMember, MembershipService
from business.contexts.identity.application.password_reset import PasswordResetService
from business.contexts.identity.application.service import IdentityService
from business.contexts.identity.application.sessions import SessionIssuer
from business.contexts.identity.domain.errors import (
    Forbidden,
    InvitationInvalid,
    LastOwner,
    ResetTokenInvalid,
)
from business.contexts.identity.domain.model import Role

from .fakes import (
    FakeClock,
    FakeHasher,
    FakeSecretBox,
    FakeTokens,
    FakeTotp,
    FakeUnitOfWork,
    RecordingNotifier,
    Store,
)

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
PASSWORD = "correct-horse-battery"


class Env:
    def __init__(self) -> None:
        self.store = Store()
        self.clock = FakeClock(NOW)
        self.notifier = RecordingNotifier()
        tokens = FakeTokens()
        hasher = FakeHasher()
        uow = lambda: FakeUnitOfWork(self.store)  # noqa: E731
        ttl = timedelta(hours=12)
        self.identity = IdentityService(uow_factory=uow, hasher=hasher, totp=FakeTotp(),
                                        secret_box=FakeSecretBox(), tokens=tokens,
                                        clock=self.clock, session_ttl=ttl)
        self.members = MembershipService(
            uow_factory=uow, hasher=hasher, tokens=tokens, notifier=self.notifier,
            clock=self.clock, sessions=SessionIssuer(tokens=tokens, clock=self.clock, ttl=ttl))
        self.resets = PasswordResetService(uow_factory=uow, hasher=hasher, tokens=tokens,
                                           notifier=self.notifier, clock=self.clock)

    async def owner(self) -> AuthContext:
        issued = await self.identity.onboard_tenant(
            OnboardTenant(email="owner@demo.uz", password=PASSWORD, tenant_name="Demo MChJ"))
        return issued.context

    async def join(self, owner: AuthContext, email: str, role: Role) -> AuthContext:
        await self.members.invite(owner, email, role)
        _, token = self.notifier.invitations[-1]
        return (await self.members.accept(token, PASSWORD)).context


@pytest.fixture
def env() -> Env:
    return Env()


async def test_invite_and_accept_creates_member_with_role(env: Env) -> None:
    owner = await env.owner()
    analyst = await env.join(owner, "ali@demo.uz", Role.ANALYST)
    assert analyst.tenant_id == owner.tenant_id and analyst.role is Role.ANALYST
    emails = {m.email: m.role for m in await env.members.list_members(owner)}
    assert emails == {"owner@demo.uz": Role.OWNER, "ali@demo.uz": Role.ANALYST}


async def test_invitation_is_single_use_and_expires(env: Env) -> None:
    owner = await env.owner()
    await env.members.invite(owner, "a@demo.uz", Role.VIEWER)
    _, token = env.notifier.invitations[-1]
    await env.members.accept(token, PASSWORD)
    with pytest.raises(InvitationInvalid):
        await env.members.accept(token, PASSWORD)

    await env.members.invite(owner, "b@demo.uz", Role.VIEWER)
    _, token = env.notifier.invitations[-1]
    env.clock.current = NOW + timedelta(days=8)
    with pytest.raises(InvitationInvalid):
        await env.members.accept(token, PASSWORD)
    with pytest.raises(NotAMember):
        await env.members.accept("unknown-token-value", PASSWORD)


async def test_existing_user_must_prove_password_to_accept(env: Env) -> None:
    owner = await env.owner()
    other = await env.identity.onboard_tenant(
        OnboardTenant(email="x@demo.uz", password=PASSWORD, tenant_name="Boshqa MChJ"))
    await env.members.invite(owner, "x@demo.uz", Role.ANALYST)
    _, token = env.notifier.invitations[-1]
    with pytest.raises(InvalidCredentials):
        await env.members.accept(token, "wrong-password-1")
    joined = await env.members.accept(token, PASSWORD)
    assert joined.context.user_id == other.context.user_id


async def test_cannot_invite_existing_member(env: Env) -> None:
    owner = await env.owner()
    with pytest.raises(AlreadyMember):
        await env.members.invite(owner, "owner@demo.uz", Role.VIEWER)


async def test_admin_permissions_are_limited(env: Env) -> None:
    owner = await env.owner()
    admin = await env.join(owner, "admin@demo.uz", Role.ADMIN)
    with pytest.raises(Forbidden):
        await env.members.invite(admin, "o2@demo.uz", Role.OWNER)
    with pytest.raises(Forbidden):
        await env.members.change_role(admin, owner.user_id, Role.VIEWER)
    viewer = await env.join(admin, "v@demo.uz", Role.VIEWER)
    await env.members.change_role(admin, viewer.user_id, Role.ANALYST)
    with pytest.raises(Forbidden):
        await env.members.list_members(viewer)


async def test_last_owner_cannot_be_demoted_or_removed(env: Env) -> None:
    owner = await env.owner()
    with pytest.raises(LastOwner):
        await env.members.change_role(owner, owner.user_id, Role.ADMIN)
    with pytest.raises(LastOwner):
        await env.members.remove(owner, owner.user_id)
    second = await env.join(owner, "o2@demo.uz", Role.OWNER)
    await env.members.change_role(owner, owner.user_id, Role.ADMIN)
    assert second.role is Role.OWNER


async def test_removed_member_session_stops_working(env: Env) -> None:
    owner = await env.owner()
    await env.members.invite(owner, "a@demo.uz", Role.ANALYST)
    _, token = env.notifier.invitations[-1]
    issued = await env.members.accept(token, PASSWORD)
    await env.members.remove(owner, issued.context.user_id)
    with pytest.raises(Exception, match="bekor"):
        await env.identity.authenticate(issued.token)


async def test_password_reset_flow(env: Env) -> None:
    owner = await env.owner()
    await env.resets.request("nobody@demo.uz")  # xato bermaydi, hech narsa yubormaydi
    assert env.notifier.resets == []
    await env.resets.request("owner@demo.uz")
    _, token = env.notifier.resets[-1]
    await env.resets.confirm(token, "brand-new-password")
    with pytest.raises(ResetTokenInvalid):
        await env.resets.confirm(token, "another-new-password")
    with pytest.raises(InvalidCredentials):
        await env.identity.login(Login(email="owner@demo.uz", password=PASSWORD))
    assert (await env.identity.login(
        Login(email="owner@demo.uz", password="brand-new-password"))).token
    assert not [s for s in env.store.sessions.values()
                if s.user_id == owner.user_id and s.created_at < NOW]


async def test_password_reset_revokes_sessions_and_expires(env: Env) -> None:
    await env.owner()
    await env.resets.request("owner@demo.uz")
    _, token = env.notifier.resets[-1]
    env.clock.current = NOW + timedelta(minutes=31)
    with pytest.raises(ResetTokenInvalid):
        await env.resets.confirm(token, "brand-new-password")
    await env.resets.request("owner@demo.uz")
    _, token = env.notifier.resets[-1]
    await env.resets.confirm(token, "brand-new-password")
    assert env.store.sessions == {}


async def test_unknown_member_is_not_found(env: Env) -> None:
    owner = await env.owner()
    with pytest.raises(NotAMember):
        await env.members.change_role(owner, uuid4(), Role.VIEWER)
