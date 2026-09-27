"""Identity use-case’lari: onboarding, login, sessiya, MFA, korxona almashtirish."""

from datetime import timedelta
from uuid import UUID, uuid4

from business.kernel.clock import Clock

from ..domain.model import (
    AuthSession,
    Email,
    Membership,
    Role,
    Tenant,
    User,
    validate_new_password,
)
from ..ports.repositories import IdentityUnitOfWork, IdentityUnitOfWorkFactory
from ..ports.security import PasswordHasher, SecretBox, SessionTokens, TotpService
from .dto import (
    AuthContext,
    IssuedSession,
    Login,
    Me,
    MfaEnrollment,
    OnboardTenant,
    TenantMembershipView,
    TenantProfile,
)
from .errors import (
    AccountLocked,
    EmailTaken,
    InvalidCredentials,
    InvalidMfaCode,
    NotAMember,
    Unauthenticated,
)
from .sessions import SessionIssuer


class IdentityService:
    def __init__(
        self,
        *,
        uow_factory: IdentityUnitOfWorkFactory,
        hasher: PasswordHasher,
        totp: TotpService,
        secret_box: SecretBox,
        tokens: SessionTokens,
        clock: Clock,
        session_ttl: timedelta,
    ) -> None:
        self._uow = uow_factory
        self._hasher = hasher
        self._totp = totp
        self._secret_box = secret_box
        self._tokens = tokens
        self._clock = clock
        self._sessions = SessionIssuer(tokens=tokens, clock=clock, ttl=session_ttl)
        # Mavjud bo‘lmagan email uchun ham hash tekshiruvi bajariladi (timing oqishi yo‘q).
        self._dummy_hash = hasher.hash(uuid4().hex)

    async def onboard_tenant(self, cmd: OnboardTenant) -> IssuedSession:
        email = Email(cmd.email)
        validate_new_password(cmd.password)
        now = self._clock.now()
        tenant = Tenant(
            id=uuid4(),
            name=cmd.tenant_name,
            timezone=cmd.timezone,
            base_currency=cmd.base_currency,
            created_at=now,
        )
        user = User(id=uuid4(), email=email, password_hash=self._hasher.hash(cmd.password),
                    created_at=now)
        membership = Membership(id=uuid4(), tenant_id=tenant.id, user_id=user.id,
                                role=Role.OWNER, created_at=now)
        async with self._uow() as uow:
            if await uow.users.get_by_email(email) is not None:
                raise EmailTaken("Bu email bilan foydalanuvchi mavjud. Tizimga kiring.")
            await uow.bind(tenant_id=tenant.id, user_id=user.id)
            await uow.users.add(user)
            await uow.tenants.add(tenant)
            await uow.memberships.add(membership)
            issued = await self._sessions.issue(uow, user, membership)
            await uow.commit()
        return issued

    async def login(self, cmd: Login) -> IssuedSession:
        email = Email(cmd.email)
        now = self._clock.now()
        async with self._uow() as uow:
            user = await uow.users.get_by_email(email)
            if user is None:
                self._hasher.verify(self._dummy_hash, cmd.password)
                raise InvalidCredentials("Email yoki parol noto‘g‘ri.")
            if user.is_locked(now):
                raise AccountLocked("Ko‘p noto‘g‘ri urinish. Birozdan keyin qayta urinib ko‘ring.")
            if not self._hasher.verify(user.password_hash, cmd.password):
                user.register_failed_login(now)
                await uow.users.save(user)
                await uow.commit()
                raise InvalidCredentials("Email yoki parol noto‘g‘ri.")

            await uow.bind(tenant_id=None, user_id=user.id)
            memberships = await uow.memberships.list_for_user(user.id)
            membership = self._pick_membership(memberships, cmd.tenant_id)
            user.register_successful_login()
            await uow.users.save(user)
            await uow.bind(tenant_id=membership.tenant_id, user_id=user.id)
            issued = await self._sessions.issue(uow, user, membership)
            await uow.commit()
        return issued

    async def authenticate(self, token: str) -> AuthContext:
        now = self._clock.now()
        async with self._uow() as uow:
            session = await uow.sessions.get_by_token_hash(self._tokens.hash(token))
            if session is None or not session.is_active(now):
                raise Unauthenticated("Sessiya tugagan. Qayta kiring.")
            await uow.bind(tenant_id=session.tenant_id, user_id=session.user_id)
            membership = await uow.memberships.get(session.tenant_id, session.user_id)
            user = await uow.users.get(session.user_id)
            if membership is None or user is None:
                # A’zolik bekor qilingan — sessiya ham yaroqsiz.
                await uow.sessions.delete(session.id)
                await uow.commit()
                raise Unauthenticated("Korxonaga kirish huquqi bekor qilingan.")
            return AuthContext(
                session_id=session.id,
                user_id=user.id,
                tenant_id=session.tenant_id,
                role=membership.role,
                mfa_satisfied=session.mfa_satisfied(user, membership.role),
            )

    async def logout(self, token: str) -> None:
        async with self._uow() as uow:
            session = await uow.sessions.get_by_token_hash(self._tokens.hash(token))
            if session is not None:
                await uow.sessions.delete(session.id)
                await uow.commit()

    async def enroll_mfa(self, ctx: AuthContext) -> MfaEnrollment:
        secret = self._totp.new_secret()
        async with self._uow() as uow:
            await uow.bind(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
            user = await self._require_user(uow, ctx.user_id)
            user.start_mfa_enrollment(self._secret_box.encrypt(secret))
            await uow.users.save(user)
            await uow.commit()
        return MfaEnrollment(
            secret=secret,
            provisioning_uri=self._totp.provisioning_uri(secret, user.email.value),
        )

    async def verify_mfa(self, ctx: AuthContext, code: str) -> AuthContext:
        now = self._clock.now()
        async with self._uow() as uow:
            await uow.bind(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
            user = await self._require_user(uow, ctx.user_id)
            if user.mfa_secret_encrypted is None:
                raise InvalidMfaCode("MFA ro‘yxatdan o‘tkazilmagan.")
            secret = self._secret_box.decrypt(user.mfa_secret_encrypted)
            step = self._totp.match_step(secret, code, now)
            if step is None:
                raise InvalidMfaCode("Kod noto‘g‘ri yoki muddati o‘tgan.")
            user.use_totp_step(step)
            if not user.mfa_enabled:
                user.confirm_mfa()
            await uow.users.save(user)
            session = await self._require_session(uow, ctx)
            session.mfa_verified = True
            await uow.sessions.save(session)
            await uow.commit()
        return AuthContext(
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            role=ctx.role,
            mfa_satisfied=True,
        )

    async def get_me(self, ctx: AuthContext) -> Me:
        async with self._uow() as uow:
            await uow.bind(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
            user = await self._require_user(uow, ctx.user_id)
            memberships = await uow.memberships.list_for_user(ctx.user_id)
            tenants = {
                t.id: t
                for t in await uow.tenants.list_by_ids([m.tenant_id for m in memberships])
            }
        return Me(
            user_id=user.id,
            email=user.email.value,
            current_tenant_id=ctx.tenant_id,
            role=ctx.role,
            mfa_enabled=user.mfa_enabled,
            mfa_satisfied=ctx.mfa_satisfied,
            memberships=[
                TenantMembershipView(tenant_id=m.tenant_id, tenant_name=tenants[m.tenant_id].name,
                                     role=m.role)
                for m in memberships
                if m.tenant_id in tenants
            ],
        )

    async def tenant_profile(self, tenant_id: UUID) -> TenantProfile:
        """Boshqa kontekstlar uchun: vaqt mintaqasi va asosiy valyuta (public API orqali)."""
        async with self._uow() as uow:
            await uow.bind(tenant_id=tenant_id, user_id=None)
            (tenant,) = await uow.tenants.list_by_ids([tenant_id])
        return TenantProfile(tenant_id=tenant.id, name=tenant.name, timezone=tenant.timezone,
                             base_currency=tenant.base_currency)

    async def role_of(self, tenant_id: UUID, user_id: UUID) -> Role | None:
        """Joriy (authoritative) rol yoki None. Delegated tool chaqiruvlari uchun."""
        async with self._uow() as uow:
            await uow.bind(tenant_id=tenant_id, user_id=user_id)
            membership = await uow.memberships.get(tenant_id, user_id)
        return membership.role if membership else None

    async def switch_tenant(self, ctx: AuthContext, tenant_id: UUID) -> IssuedSession:
        """Yangi tenant kontekstli sessiya beradi va eskisini yopadi."""
        async with self._uow() as uow:
            await uow.bind(tenant_id=None, user_id=ctx.user_id)
            membership = await uow.memberships.get(tenant_id, ctx.user_id)
            if membership is None:
                raise NotAMember("Korxona topilmadi.")
            user = await self._require_user(uow, ctx.user_id)
            old = await self._require_session(uow, ctx)
            await uow.sessions.delete(old.id)
            await uow.bind(tenant_id=tenant_id, user_id=ctx.user_id)
            issued = await self._sessions.issue(uow, user, membership,
                                                mfa_verified=old.mfa_verified)
            await uow.commit()
        return issued

    @staticmethod
    def _pick_membership(memberships: list[Membership], tenant_id: UUID | None) -> Membership:
        if not memberships:
            raise InvalidCredentials("Foydalanuvchi hech bir korxonaga a’zo emas.")
        if tenant_id is None:
            return min(memberships, key=lambda m: m.created_at)
        for membership in memberships:
            if membership.tenant_id == tenant_id:
                return membership
        raise NotAMember("Korxona topilmadi.")

    @staticmethod
    async def _require_user(uow: IdentityUnitOfWork, user_id: UUID) -> User:
        return await require_user(uow, user_id)

    @staticmethod
    async def _require_session(uow: IdentityUnitOfWork, ctx: AuthContext) -> AuthSession:
        session = await uow.sessions.get_by_id(ctx.session_id)
        if session is None:
            raise Unauthenticated("Sessiya tugagan. Qayta kiring.")
        return session


async def require_user(uow: IdentityUnitOfWork, user_id: UUID) -> User:
    user = await uow.users.get(user_id)
    if user is None:
        raise Unauthenticated("Foydalanuvchi topilmadi.")
    return user
