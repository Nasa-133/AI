"""In-memory adapterlar: application qatlamini DB va tarmoqsiz testlash uchun."""

import copy
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from business.contexts.identity.domain.model import (
    AuthSession,
    Email,
    Invitation,
    Membership,
    PasswordResetToken,
    Role,
    Tenant,
    User,
)


class Store:
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.tenants: dict[UUID, Tenant] = {}
        self.memberships: dict[UUID, Membership] = {}
        self.sessions: dict[UUID, AuthSession] = {}
        self.invitations: dict[UUID, Invitation] = {}
        self.password_resets: dict[UUID, PasswordResetToken] = {}


class _Users:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def get(self, user_id: UUID) -> User | None:
        return copy.deepcopy(self.s.users.get(user_id))

    async def get_many(self, user_ids: list[UUID]) -> list[User]:
        return [copy.deepcopy(self.s.users[i]) for i in user_ids if i in self.s.users]

    async def get_by_email(self, email: Email) -> User | None:
        return next((copy.deepcopy(u) for u in self.s.users.values() if u.email == email), None)

    async def add(self, user: User) -> None:
        self.s.users[user.id] = copy.deepcopy(user)

    async def save(self, user: User) -> None:
        self.s.users[user.id] = copy.deepcopy(user)


class _Tenants:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def add(self, tenant: Tenant) -> None:
        self.s.tenants[tenant.id] = tenant

    async def list_by_ids(self, tenant_ids: list[UUID]) -> list[Tenant]:
        return [self.s.tenants[i] for i in tenant_ids if i in self.s.tenants]


class _Memberships:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def add(self, membership: Membership) -> None:
        self.s.memberships[membership.id] = membership

    async def get(self, tenant_id: UUID, user_id: UUID) -> Membership | None:
        return next(
            (m for m in self.s.memberships.values()
             if m.tenant_id == tenant_id and m.user_id == user_id),
            None,
        )

    async def list_for_user(self, user_id: UUID) -> list[Membership]:
        return sorted((m for m in self.s.memberships.values() if m.user_id == user_id),
                      key=lambda m: m.created_at)

    async def list_for_tenant(self, tenant_id: UUID) -> list[Membership]:
        return sorted((m for m in self.s.memberships.values() if m.tenant_id == tenant_id),
                      key=lambda m: m.created_at)

    async def count_owners(self, tenant_id: UUID) -> int:
        return sum(1 for m in self.s.memberships.values()
                   if m.tenant_id == tenant_id and m.role is Role.OWNER)

    async def save(self, membership: Membership) -> None:
        self.s.memberships[membership.id] = membership

    async def delete(self, membership_id: UUID) -> None:
        self.s.memberships.pop(membership_id, None)


class _Sessions:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def add(self, session: AuthSession) -> None:
        self.s.sessions[session.id] = copy.deepcopy(session)

    async def get_by_id(self, session_id: UUID) -> AuthSession | None:
        return copy.deepcopy(self.s.sessions.get(session_id))

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        return next((copy.deepcopy(x) for x in self.s.sessions.values()
                     if x.token_hash == token_hash), None)

    async def save(self, session: AuthSession) -> None:
        self.s.sessions[session.id] = copy.deepcopy(session)

    async def delete(self, session_id: UUID) -> None:
        self.s.sessions.pop(session_id, None)

    async def delete_for_user(self, user_id: UUID) -> None:
        for sid in [k for k, v in self.s.sessions.items() if v.user_id == user_id]:
            del self.s.sessions[sid]


class _Invitations:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def add(self, invitation: Invitation) -> None:
        self.s.invitations[invitation.id] = copy.deepcopy(invitation)

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        return next((copy.deepcopy(i) for i in self.s.invitations.values()
                     if i.token_hash == token_hash), None)

    async def list_pending(self, tenant_id: UUID) -> list[Invitation]:
        return [copy.deepcopy(i) for i in self.s.invitations.values()
                if i.tenant_id == tenant_id and i.accepted_at is None]

    async def save(self, invitation: Invitation) -> None:
        self.s.invitations[invitation.id] = copy.deepcopy(invitation)


class _PasswordResets:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def add(self, token: PasswordResetToken) -> None:
        self.s.password_resets[token.id] = copy.deepcopy(token)

    async def get_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        return next((copy.deepcopy(t) for t in self.s.password_resets.values()
                     if t.token_hash == token_hash), None)

    async def save(self, token: PasswordResetToken) -> None:
        self.s.password_resets[token.id] = copy.deepcopy(token)


class FakeUnitOfWork:
    """Commit qilinmagan o‘zgarishlar tashlab yuboriladi — haqiqiy tranzaksiya kabi."""

    def __init__(self, committed: Store) -> None:
        self._committed = committed

    async def __aenter__(self) -> Self:
        self._work = copy.deepcopy(self._committed)
        self.users = _Users(self._work)
        self.tenants = _Tenants(self._work)
        self.memberships = _Memberships(self._work)
        self.sessions = _Sessions(self._work)
        self.invitations = _Invitations(self._work)
        self.password_resets = _PasswordResets(self._work)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def bind(self, *, tenant_id: UUID | None, user_id: UUID | None,
                   invitation_token_hash: str | None = None) -> None:
        return None

    async def commit(self) -> None:
        self._committed.__dict__.update(copy.deepcopy(self._work).__dict__)


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"hashed:{password}"


class FakeTotp:
    """Kod = vaqt qadami (30 soniyalik) raqami, 6 xonali."""

    def new_secret(self) -> str:
        return "SECRET"

    @staticmethod
    def code_at(now: datetime) -> str:
        return f"{int(now.timestamp()) // 30 % 1_000_000:06d}"

    def match_step(self, secret: str, code: str, now: datetime) -> int | None:
        step = int(now.timestamp()) // 30
        return step if secret == "SECRET" and code == self.code_at(now) else None

    def provisioning_uri(self, secret: str, account: str) -> str:
        return f"otpauth://totp/{account}?secret={secret}"


class FakeSecretBox:
    def encrypt(self, plaintext: str) -> str:
        return f"enc:{plaintext}"

    def decrypt(self, ciphertext: str) -> str:
        return ciphertext.removeprefix("enc:")


class FakeTokens:
    def __init__(self) -> None:
        self._n = 0

    def new_token(self) -> str:
        self._n += 1
        return f"token-{self._n}"

    def hash(self, token: str) -> str:
        return f"h:{token}"


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


class RecordingNotifier:
    def __init__(self) -> None:
        self.invitations: list[tuple[str, str]] = []
        self.resets: list[tuple[str, str]] = []

    async def send_invitation(self, *, email: str, tenant_name: str, token: str) -> None:
        self.invitations.append((email, token))

    async def send_password_reset(self, *, email: str, token: str) -> None:
        self.resets.append((email, token))
