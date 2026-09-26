"""Identity & Access domeni: foydalanuvchi, korxona, a’zolik va sessiya invariantlari."""

import re
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from functools import cache
from uuid import UUID

from .errors import InvalidEmail, InvalidTenant, MfaAlreadyEnabled, MfaNotEnrolled, WeakPassword

MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"

    @property
    def requires_mfa(self) -> bool:
        return self in (Role.OWNER, Role.ADMIN)


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if len(normalized) > 254 or not _EMAIL_RE.fullmatch(normalized):
            raise InvalidEmail("Email manzili noto‘g‘ri.")
        object.__setattr__(self, "value", normalized)


def validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(f"Parol kamida {MIN_PASSWORD_LENGTH} belgidan iborat bo‘lishi kerak.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPassword("Parol juda uzun.")


@cache
def _known_timezones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


@dataclass(slots=True)
class Tenant:
    id: UUID
    name: str
    timezone: str
    base_currency: str
    created_at: datetime

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not 2 <= len(self.name) <= 200:
            raise InvalidTenant("Korxona nomi 2–200 belgi bo‘lishi kerak.")
        if self.timezone not in _known_timezones():
            raise InvalidTenant(f"Noma’lum vaqt mintaqasi: {self.timezone}")
        if not _CURRENCY_RE.fullmatch(self.base_currency):
            raise InvalidTenant("Valyuta ISO 4217 kodi bo‘lishi kerak, masalan UZS.")


@dataclass(slots=True)
class User:
    id: UUID
    email: Email
    password_hash: str
    created_at: datetime
    mfa_secret_encrypted: str | None = None
    mfa_enabled: bool = False
    failed_login_count: int = 0
    locked_until: datetime | None = None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until

    def register_failed_login(self, now: datetime) -> None:
        self.failed_login_count += 1
        if self.failed_login_count >= MAX_FAILED_LOGINS:
            self.locked_until = now + LOCKOUT_DURATION
            self.failed_login_count = 0

    def register_successful_login(self) -> None:
        self.failed_login_count = 0
        self.locked_until = None

    def start_mfa_enrollment(self, encrypted_secret: str) -> None:
        if self.mfa_enabled:
            raise MfaAlreadyEnabled("MFA allaqachon yoqilgan.")
        self.mfa_secret_encrypted = encrypted_secret

    def confirm_mfa(self) -> None:
        if self.mfa_secret_encrypted is None:
            raise MfaNotEnrolled("Avval MFA’ni ro‘yxatdan o‘tkazing.")
        self.mfa_enabled = True


@dataclass(frozen=True, slots=True)
class Membership:
    id: UUID
    tenant_id: UUID
    user_id: UUID
    role: Role
    created_at: datetime


@dataclass(slots=True)
class AuthSession:
    id: UUID
    token_hash: str
    user_id: UUID
    tenant_id: UUID
    created_at: datetime
    expires_at: datetime
    mfa_verified: bool = False

    def is_active(self, now: datetime) -> bool:
        return now < self.expires_at

    def mfa_satisfied(self, user: User, role: Role) -> bool:
        """MFA talab qilinmasa yoki bu sessiyada tasdiqlangan bo‘lsa True."""
        if role.requires_mfa or user.mfa_enabled:
            return self.mfa_verified
        return True
