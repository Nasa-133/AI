"""In-memory adapterlar: application qatlamini DB va tarmoqsiz testlash uchun."""

import copy
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from business.contexts.identity.domain.model import AuthSession, Email, Membership, Tenant, User


class Store:
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.tenants: dict[UUID, Tenant] = {}
        self.memberships: dict[UUID, Membership] = {}
        self.sessions: dict[UUID, AuthSession] = {}


class _Users:
    def __init__(self, s: Store) -> None:
        self.s = s

    async def get(self, user_id: UUID) -> User | None:
        return copy.deepcopy(self.s.users.get(user_id))

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
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def bind(self, *, tenant_id: UUID | None, user_id: UUID | None) -> None:
        return None

    async def commit(self) -> None:
        self._committed.__dict__.update(copy.deepcopy(self._work).__dict__)


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"hashed:{password}"


class FakeTotp:
    VALID_CODE = "123456"

    def new_secret(self) -> str:
        return "SECRET"

    def verify(self, secret: str, code: str, now: datetime) -> bool:
        return secret == "SECRET" and code == self.VALID_CODE

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
