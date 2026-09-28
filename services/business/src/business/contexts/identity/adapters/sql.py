"""PostgreSQL adapterlari. Domain obyekti ↔ jadval satri mapping’i shu yerda."""

from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self
from uuid import UUID

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction

from business.platform.db import bind_request_context

from ..application.errors import EmailTaken
from ..domain.model import (
    AuthSession,
    Email,
    Invitation,
    Membership,
    PasswordResetToken,
    Role,
    Tenant,
    User,
)
from . import tables as t


def _now() -> datetime:
    return datetime.now(UTC)


def _user_from_row(row: RowMapping) -> User:
    return User(
        id=row["id"],
        email=Email(row["email"]),
        password_hash=row["password_hash"],
        created_at=row["created_at"],
        mfa_secret_encrypted=row["mfa_secret_encrypted"],
        mfa_enabled=row["mfa_enabled"],
        failed_login_count=row["failed_login_count"],
        locked_until=row["locked_until"],
        mfa_last_used_step=row["mfa_last_used_step"],
    )


def _user_values(user: User) -> dict[str, Any]:
    return {
        "email": user.email.value,
        "password_hash": user.password_hash,
        "mfa_secret_encrypted": user.mfa_secret_encrypted,
        "mfa_enabled": user.mfa_enabled,
        "failed_login_count": user.failed_login_count,
        "locked_until": user.locked_until,
        "mfa_last_used_step": user.mfa_last_used_step,
        "updated_at": _now(),
    }


def _session_from_row(row: RowMapping) -> AuthSession:
    return AuthSession(
        id=row["id"],
        token_hash=row["token_hash"],
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        mfa_verified=row["mfa_verified"],
    )


def _membership_from_row(row: RowMapping) -> Membership:
    return Membership(
        id=row["id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        role=Role(row["role"]),
        created_at=row["created_at"],
        branch_scope=tuple(row["branch_scope"]) if row["branch_scope"] is not None else None,
    )


class SqlUserRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def get(self, user_id: UUID) -> User | None:
        row = (await self._conn.execute(select(t.users).where(t.users.c.id == user_id))).mappings()
        found = row.first()
        return _user_from_row(found) if found else None

    async def get_many(self, user_ids: list[UUID]) -> list[User]:
        if not user_ids:
            return []
        result = await self._conn.execute(select(t.users).where(t.users.c.id.in_(user_ids)))
        return [_user_from_row(r) for r in result.mappings()]

    async def get_by_email(self, email: Email) -> User | None:
        result = await self._conn.execute(select(t.users).where(t.users.c.email == email.value))
        found = result.mappings().first()
        return _user_from_row(found) if found else None

    async def add(self, user: User) -> None:
        try:
            async with self._conn.begin_nested():
                await self._conn.execute(
                    insert(t.users).values(
                        id=user.id, created_at=user.created_at, **_user_values(user)
                    )
                )
        except IntegrityError as exc:
            # Parallel onboarding: tekshiruvdan keyin boshqa so‘rov shu emailni band qilgan.
            raise EmailTaken("Bu email bilan foydalanuvchi mavjud. Tizimga kiring.") from exc

    async def save(self, user: User) -> None:
        await self._conn.execute(
            update(t.users).where(t.users.c.id == user.id).values(**_user_values(user))
        )


class SqlTenantRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, tenant: Tenant) -> None:
        await self._conn.execute(
            insert(t.tenants).values(
                id=tenant.id,
                name=tenant.name,
                timezone=tenant.timezone,
                base_currency=tenant.base_currency,
                created_at=tenant.created_at,
                updated_at=tenant.created_at,
            )
        )

    async def list_by_ids(self, tenant_ids: list[UUID]) -> list[Tenant]:
        if not tenant_ids:
            return []
        result = await self._conn.execute(select(t.tenants).where(t.tenants.c.id.in_(tenant_ids)))
        return [
            Tenant(
                id=r["id"],
                name=r["name"],
                timezone=r["timezone"],
                base_currency=r["base_currency"],
                created_at=r["created_at"],
            )
            for r in result.mappings()
        ]


class SqlMembershipRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, membership: Membership) -> None:
        await self._conn.execute(
            insert(t.memberships).values(
                id=membership.id,
                tenant_id=membership.tenant_id,
                user_id=membership.user_id,
                role=membership.role.value,
                created_at=membership.created_at,
                updated_at=membership.created_at,
            )
        )

    async def get(self, tenant_id: UUID, user_id: UUID) -> Membership | None:
        result = await self._conn.execute(
            select(t.memberships).where(
                t.memberships.c.tenant_id == tenant_id, t.memberships.c.user_id == user_id
            )
        )
        found = result.mappings().first()
        return _membership_from_row(found) if found else None

    async def list_for_user(self, user_id: UUID) -> list[Membership]:
        result = await self._conn.execute(
            select(t.memberships)
            .where(t.memberships.c.user_id == user_id)
            .order_by(t.memberships.c.created_at)
        )
        return [_membership_from_row(r) for r in result.mappings()]

    async def list_for_tenant(self, tenant_id: UUID) -> list[Membership]:
        result = await self._conn.execute(
            select(t.memberships)
            .where(t.memberships.c.tenant_id == tenant_id)
            .order_by(t.memberships.c.created_at)
        )
        return [_membership_from_row(r) for r in result.mappings()]

    async def count_owners(self, tenant_id: UUID) -> int:
        result = await self._conn.execute(
            select(func.count()).select_from(t.memberships).where(
                t.memberships.c.tenant_id == tenant_id, t.memberships.c.role == Role.OWNER.value
            )
        )
        return int(result.scalar_one())

    async def save(self, membership: Membership) -> None:
        await self._conn.execute(
            update(t.memberships)
            .where(t.memberships.c.id == membership.id)
            .values(
                role=membership.role.value,
                updated_at=_now(),
                branch_scope=list(membership.branch_scope)
                if membership.branch_scope is not None
                else None,
            )
        )

    async def delete(self, membership_id: UUID) -> None:
        await self._conn.execute(delete(t.memberships).where(t.memberships.c.id == membership_id))


class SqlSessionRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, session: AuthSession) -> None:
        await self._conn.execute(
            insert(t.sessions).values(
                id=session.id,
                token_hash=session.token_hash,
                user_id=session.user_id,
                tenant_id=session.tenant_id,
                mfa_verified=session.mfa_verified,
                created_at=session.created_at,
                expires_at=session.expires_at,
            )
        )

    async def get_by_id(self, session_id: UUID) -> AuthSession | None:
        result = await self._conn.execute(select(t.sessions).where(t.sessions.c.id == session_id))
        found = result.mappings().first()
        return _session_from_row(found) if found else None

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        result = await self._conn.execute(
            select(t.sessions).where(t.sessions.c.token_hash == token_hash)
        )
        found = result.mappings().first()
        return _session_from_row(found) if found else None

    async def save(self, session: AuthSession) -> None:
        await self._conn.execute(
            update(t.sessions)
            .where(t.sessions.c.id == session.id)
            .values(mfa_verified=session.mfa_verified, expires_at=session.expires_at)
        )

    async def delete(self, session_id: UUID) -> None:
        await self._conn.execute(delete(t.sessions).where(t.sessions.c.id == session_id))

    async def delete_for_user(self, user_id: UUID) -> None:
        await self._conn.execute(delete(t.sessions).where(t.sessions.c.user_id == user_id))


def _invitation_from_row(row: RowMapping) -> Invitation:
    return Invitation(
        id=row["id"],
        tenant_id=row["tenant_id"],
        email=Email(row["email"]),
        role=Role(row["role"]),
        token_hash=row["token_hash"],
        invited_by=row["invited_by"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        accepted_at=row["accepted_at"],
    )


class SqlInvitationRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, invitation: Invitation) -> None:
        await self._conn.execute(
            insert(t.invitations).values(
                id=invitation.id,
                tenant_id=invitation.tenant_id,
                email=invitation.email.value,
                role=invitation.role.value,
                token_hash=invitation.token_hash,
                invited_by=invitation.invited_by,
                created_at=invitation.created_at,
                updated_at=invitation.created_at,
                expires_at=invitation.expires_at,
                accepted_at=invitation.accepted_at,
            )
        )

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        result = await self._conn.execute(
            select(t.invitations).where(t.invitations.c.token_hash == token_hash)
        )
        found = result.mappings().first()
        return _invitation_from_row(found) if found else None

    async def list_pending(self, tenant_id: UUID) -> list[Invitation]:
        result = await self._conn.execute(
            select(t.invitations)
            .where(t.invitations.c.tenant_id == tenant_id, t.invitations.c.accepted_at.is_(None))
            .order_by(t.invitations.c.created_at)
        )
        return [_invitation_from_row(r) for r in result.mappings()]

    async def save(self, invitation: Invitation) -> None:
        await self._conn.execute(
            update(t.invitations)
            .where(t.invitations.c.id == invitation.id)
            .values(accepted_at=invitation.accepted_at, updated_at=_now())
        )


class SqlPasswordResetRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, token: PasswordResetToken) -> None:
        await self._conn.execute(
            insert(t.password_reset_tokens).values(
                id=token.id,
                user_id=token.user_id,
                token_hash=token.token_hash,
                created_at=token.created_at,
                expires_at=token.expires_at,
                used_at=token.used_at,
            )
        )

    async def get_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        result = await self._conn.execute(
            select(t.password_reset_tokens).where(
                t.password_reset_tokens.c.token_hash == token_hash
            )
        )
        r = result.mappings().first()
        if r is None:
            return None
        return PasswordResetToken(id=r["id"], user_id=r["user_id"], token_hash=r["token_hash"],
                                  created_at=r["created_at"], expires_at=r["expires_at"],
                                  used_at=r["used_at"])

    async def save(self, token: PasswordResetToken) -> None:
        await self._conn.execute(
            update(t.password_reset_tokens)
            .where(t.password_reset_tokens.c.id == token.id)
            .values(used_at=token.used_at)
        )


class SqlIdentityUnitOfWork:
    users: SqlUserRepository
    tenants: SqlTenantRepository
    memberships: SqlMembershipRepository
    sessions: SqlSessionRepository
    invitations: SqlInvitationRepository
    password_resets: SqlPasswordResetRepository

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._conn: AsyncConnection | None = None
        self._tx: AsyncTransaction | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        self._conn = await self._engine.connect()
        self._tx = await self._conn.begin()
        self.users = SqlUserRepository(self._conn)
        self.tenants = SqlTenantRepository(self._conn)
        self.memberships = SqlMembershipRepository(self._conn)
        self.sessions = SqlSessionRepository(self._conn)
        self.invitations = SqlInvitationRepository(self._conn)
        self.password_resets = SqlPasswordResetRepository(self._conn)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._conn is not None and self._tx is not None
        try:
            if not self._committed and self._tx.is_active:
                await self._tx.rollback()
        finally:
            await self._conn.close()

    async def bind(
        self,
        *,
        tenant_id: UUID | None,
        user_id: UUID | None,
        invitation_token_hash: str | None = None,
    ) -> None:
        assert self._conn is not None
        await bind_request_context(self._conn, tenant_id=tenant_id, user_id=user_id)
        await self._conn.execute(
            text("SELECT set_config('app.invitation_token_hash', :h, true)"),
            {"h": invitation_token_hash or ""},
        )

    async def commit(self) -> None:
        assert self._tx is not None
        await self._tx.commit()
        self._committed = True


class SqlIdentityUnitOfWorkFactory:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    def __call__(self) -> SqlIdentityUnitOfWork:
        return SqlIdentityUnitOfWork(self._engine)
