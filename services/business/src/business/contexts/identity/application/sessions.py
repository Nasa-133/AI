from datetime import timedelta
from uuid import uuid4

from business.kernel.clock import Clock

from ..domain.model import AuthSession, Membership, User
from ..ports.repositories import IdentityUnitOfWork
from ..ports.security import SessionTokens
from .dto import AuthContext, IssuedSession


class SessionIssuer:
    """Login, korxona almashtirish va taklifni qabul qilishda yagona sessiya yaratish qoidasi."""

    def __init__(self, *, tokens: SessionTokens, clock: Clock, ttl: timedelta) -> None:
        self._tokens = tokens
        self._clock = clock
        self._ttl = ttl

    async def issue(
        self,
        uow: IdentityUnitOfWork,
        user: User,
        membership: Membership,
        *,
        mfa_verified: bool = False,
    ) -> IssuedSession:
        now = self._clock.now()
        token = self._tokens.new_token()
        session = AuthSession(
            id=uuid4(),
            token_hash=self._tokens.hash(token),
            user_id=user.id,
            tenant_id=membership.tenant_id,
            created_at=now,
            expires_at=now + self._ttl,
            mfa_verified=mfa_verified,
        )
        await uow.sessions.add(session)
        return IssuedSession(
            token=token,
            expires_at=session.expires_at,
            context=AuthContext(
                session_id=session.id,
                user_id=user.id,
                tenant_id=membership.tenant_id,
                role=membership.role,
                mfa_satisfied=session.mfa_satisfied(user, membership.role),
            ),
        )
