from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..domain.model import Role


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Har so‘rovda DB’dan qayta tekshirilgan identity konteksti."""

    session_id: UUID
    user_id: UUID
    tenant_id: UUID
    role: Role
    mfa_satisfied: bool


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    expires_at: datetime
    context: AuthContext


@dataclass(frozen=True, slots=True)
class OnboardTenant:
    email: str
    password: str
    tenant_name: str
    timezone: str = "Asia/Tashkent"
    base_currency: str = "UZS"


@dataclass(frozen=True, slots=True)
class Login:
    email: str
    password: str
    tenant_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class MfaEnrollment:
    secret: str
    provisioning_uri: str


@dataclass(frozen=True, slots=True)
class TenantMembershipView:
    tenant_id: UUID
    tenant_name: str
    role: Role


@dataclass(frozen=True, slots=True)
class Me:
    user_id: UUID
    email: str
    current_tenant_id: UUID
    role: Role
    mfa_enabled: bool
    mfa_satisfied: bool
    memberships: list[TenantMembershipView]
