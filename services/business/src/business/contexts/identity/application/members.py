"""A’zolar va takliflar (TZ 3): taklif, qabul qilish, rolni o‘zgartirish, chiqarish."""

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from business.kernel.clock import Clock
from business.kernel.errors import BusinessError

from ..domain.errors import Forbidden
from ..domain.model import (
    INVITATION_TTL,
    Email,
    Invitation,
    Membership,
    Role,
    User,
    ensure_can_assign_role,
    ensure_can_change_member,
    normalize_branch_scope,
    validate_new_password,
)
from ..ports.repositories import IdentityUnitOfWorkFactory
from ..ports.security import IdentityNotifier, PasswordHasher, SessionTokens
from .dto import AuthContext, IssuedSession
from .errors import InvalidCredentials, NotAMember
from .sessions import SessionIssuer

logger = logging.getLogger(__name__)


class AlreadyMember(BusinessError):
    code = "ALREADY_MEMBER"


@dataclass(frozen=True, slots=True)
class MemberView:
    user_id: UUID
    email: str
    role: Role
    joined_at: datetime
    branch_scope: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class InvitationView:
    id: UUID
    email: str
    role: Role
    expires_at: datetime


def _require_manager(ctx: AuthContext) -> None:
    if ctx.role not in (Role.OWNER, Role.ADMIN):
        raise Forbidden("Bu amal faqat Owner yoki Admin uchun.")


class MembershipService:
    def __init__(
        self,
        *,
        uow_factory: IdentityUnitOfWorkFactory,
        hasher: PasswordHasher,
        tokens: SessionTokens,
        notifier: IdentityNotifier,
        clock: Clock,
        sessions: SessionIssuer,
    ) -> None:
        self._uow = uow_factory
        self._hasher = hasher
        self._tokens = tokens
        self._notifier = notifier
        self._clock = clock
        self._sessions = sessions

    async def invite(self, ctx: AuthContext, email: str, role: Role) -> InvitationView:
        ensure_can_assign_role(ctx.role, role)
        address = Email(email)
        now = self._clock.now()
        token = self._tokens.new_token()
        invitation = Invitation(
            id=uuid4(),
            tenant_id=ctx.tenant_id,
            email=address,
            role=role,
            token_hash=self._tokens.hash(token),
            invited_by=ctx.user_id,
            created_at=now,
            expires_at=now + INVITATION_TTL,
        )
        async with self._uow() as uow:
            await uow.bind(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
            existing = await uow.users.get_by_email(address)
            if existing and await uow.memberships.get(ctx.tenant_id, existing.id):
                raise AlreadyMember("Bu foydalanuvchi allaqachon korxona a’zosi.")
            await uow.invitations.add(invitation)
            (tenant,) = await uow.tenants.list_by_ids([ctx.tenant_id])
            await uow.commit()
        # Tashqi yuborish commitdan keyin: xato bo‘lsa taklif saqlanadi va qayta yuborish mumkin.
        try:
            await self._notifier.send_invitation(email=address.value, tenant_name=tenant.name,
                                                 token=token)
        except Exception:
            logger.exception("Taklifni yuborib bo‘lmadi", extra={"invitation_id": invitation.id})
        return InvitationView(id=invitation.id, email=address.value, role=role,
                              expires_at=invitation.expires_at)

    async def list_invitations(self, ctx: AuthContext) -> list[InvitationView]:
        _require_manager(ctx)
        async with self._uow() as uow:
            await uow.bind(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
            pending = await uow.invitations.list_pending(ctx.tenant_id)
        now = self._clock.now()
        return [
            InvitationView(id=i.id, email=i.email.value, role=i.role, expires_at=i.expires_at)
            for i in pending
            if i.expires_at > now
        ]

    async def accept(self, token: str, password: str) -> IssuedSession:
        """Yangi foydalanuvchi parol o‘rnatadi; mavjud foydalanuvchi o‘z parolini kiritadi."""
        token_hash = self._tokens.hash(token)
        now = self._clock.now()
        async with self._uow() as uow:
            await uow.bind(tenant_id=None, user_id=None, invitation_token_hash=token_hash)
            invitation = await uow.invitations.get_by_token_hash(token_hash)
            if invitation is None:
                raise NotAMember("Taklif topilmadi.")
            invitation.accept(now)

            user = await uow.users.get_by_email(invitation.email)
            if user is None:
                validate_new_password(password)
                user = User(id=uuid4(), email=invitation.email,
                            password_hash=self._hasher.hash(password), created_at=now)
                await uow.users.add(user)
            elif not self._hasher.verify(user.password_hash, password):
                raise InvalidCredentials("Parol noto‘g‘ri.")

            await uow.bind(tenant_id=invitation.tenant_id, user_id=user.id,
                           invitation_token_hash=token_hash)
            membership = await uow.memberships.get(invitation.tenant_id, user.id)
            if membership is None:
                membership = Membership(id=uuid4(), tenant_id=invitation.tenant_id,
                                        user_id=user.id, role=invitation.role, created_at=now)
                await uow.memberships.add(membership)
            await uow.invitations.save(invitation)
            issued = await self._sessions.issue(uow, user, membership)
            await uow.commit()
        return issued

    async def list_members(self, ctx: AuthContext) -> list[MemberView]:
        _require_manager(ctx)
        async with self._uow() as uow:
            await uow.bind(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
            memberships = await uow.memberships.list_for_tenant(ctx.tenant_id)
            users = {u.id: u for u in await uow.users.get_many([m.user_id for m in memberships])}
        return [
            MemberView(user_id=m.user_id, email=users[m.user_id].email.value, role=m.role,
                       joined_at=m.created_at, branch_scope=m.branch_scope)
            for m in memberships
            if m.user_id in users
        ]

    async def change_role(self, ctx: AuthContext, user_id: UUID, role: Role) -> MemberView:
        async with self._uow() as uow:
            await uow.bind(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
            target = await uow.memberships.get(ctx.tenant_id, user_id)
            if target is None:
                raise NotAMember("A’zo topilmadi.")
            ensure_can_change_member(
                actor=ctx.role, target=target.role, new_role=role,
                owners_count=await uow.memberships.count_owners(ctx.tenant_id),
            )
            # Owner/Admin’ga ko‘tarilsa filial doirasi olib tashlanadi (ular hammasini ko‘radi).
            scope = None if role in (Role.OWNER, Role.ADMIN) else target.branch_scope
            updated = Membership(id=target.id, tenant_id=target.tenant_id,
                                 user_id=target.user_id, role=role, created_at=target.created_at,
                                 branch_scope=scope)
            await uow.memberships.save(updated)
            user = await uow.users.get(user_id)
            await uow.commit()
        assert user is not None
        return MemberView(user_id=user_id, email=user.email.value, role=role,
                          joined_at=updated.created_at, branch_scope=scope)

    async def set_branch_scope(self, ctx: AuthContext, user_id: UUID,
                               codes: list[str] | None) -> MemberView:
        """S02: a’zo faqat shu filiallar ma’lumotini ko‘radi (None — barchasi)."""
        async with self._uow() as uow:
            await uow.bind(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
            target = await uow.memberships.get(ctx.tenant_id, user_id)
            if target is None:
                raise NotAMember("A’zo topilmadi.")
            ensure_can_change_member(
                actor=ctx.role, target=target.role, new_role=target.role,
                owners_count=await uow.memberships.count_owners(ctx.tenant_id),
            )
            scope = normalize_branch_scope(target.role, codes)
            await uow.memberships.save(Membership(
                id=target.id, tenant_id=target.tenant_id, user_id=target.user_id,
                role=target.role, created_at=target.created_at, branch_scope=scope))
            user = await uow.users.get(user_id)
            await uow.commit()
        assert user is not None
        return MemberView(user_id=user_id, email=user.email.value, role=target.role,
                          joined_at=target.created_at, branch_scope=scope)

    async def remove(self, ctx: AuthContext, user_id: UUID) -> None:
        """A’zolik o‘chiriladi; uning sessiyalari keyingi so‘rovda avtomatik yaroqsiz bo‘ladi."""
        async with self._uow() as uow:
            await uow.bind(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
            target = await uow.memberships.get(ctx.tenant_id, user_id)
            if target is None:
                raise NotAMember("A’zo topilmadi.")
            ensure_can_change_member(
                actor=ctx.role, target=target.role, new_role=None,
                owners_count=await uow.memberships.count_owners(ctx.tenant_id),
            )
            await uow.memberships.delete(target.id)
            await uow.commit()
