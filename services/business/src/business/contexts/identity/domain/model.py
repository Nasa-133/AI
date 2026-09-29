"""Identity & Access domeni: foydalanuvchi, korxona, a’zolik va sessiya invariantlari."""

import re
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from functools import cache
from uuid import UUID

from .errors import (
    Forbidden,
    InvalidBranchScope,
    InvalidEmail,
    InvalidTenant,
    InvitationInvalid,
    LastOwner,
    MfaAlreadyEnabled,
    MfaCodeReused,
    MfaNotEnrolled,
    ResetTokenInvalid,
    WeakPassword,
)

MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
MIN_PASSWORD_LENGTH = 10
INVITATION_TTL = timedelta(days=7)
PASSWORD_RESET_TTL = timedelta(minutes=30)
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
    mfa_last_used_step: int | None = None

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

    def reset_mfa(self) -> None:
        """Administrator tiklashi: foydalanuvchi keyingi kirishda 2FA’ni qaytadan sozlaydi."""
        self.mfa_secret_encrypted = None
        self.mfa_enabled = False
        self.mfa_last_used_step = None

    def use_totp_step(self, step: int) -> None:
        """Bir TOTP kodi (vaqt qadami) ikki marta qabul qilinmaydi."""
        if self.mfa_last_used_step is not None and step <= self.mfa_last_used_step:
            raise MfaCodeReused("Bu kod allaqachon ishlatilgan. Keyingi kodni kiriting.")
        self.mfa_last_used_step = step

    def change_password(self, new_hash: str) -> None:
        self.password_hash = new_hash
        self.register_successful_login()


@dataclass(frozen=True, slots=True)
class Membership:
    id: UUID
    tenant_id: UUID
    user_id: UUID
    role: Role
    created_at: datetime
    # S02: None — barcha filiallar; Owner/Admin uchun doim None.
    branch_scope: tuple[str, ...] | None = None


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


def ensure_can_assign_role(actor: Role, role: Role) -> None:
    """Owner istalgan rolni beradi; Admin faqat Analyst/Viewer (TZ 3-bo‘lim)."""
    if actor is Role.OWNER:
        return
    if actor is Role.ADMIN and role in (Role.ANALYST, Role.VIEWER):
        return
    raise Forbidden("Bu rolni berish uchun vakolat yetarli emas.")


def ensure_can_change_member(
    *, actor: Role, target: Role, new_role: Role | None, owners_count: int
) -> None:
    """`new_role=None` — a’zoni chiqarish. Korxonada kamida bitta Owner qoladi."""
    if actor not in (Role.OWNER, Role.ADMIN):
        raise Forbidden("A’zolarni boshqarish uchun vakolat yetarli emas.")
    if actor is Role.ADMIN and target in (Role.OWNER, Role.ADMIN):
        raise Forbidden("Admin Owner yoki boshqa Admin’ni o‘zgartira olmaydi.")
    if new_role is not None:
        ensure_can_assign_role(actor, new_role)
    if target is Role.OWNER and new_role is not Role.OWNER and owners_count <= 1:
        raise LastOwner("Korxonada kamida bitta Owner qolishi kerak.")


BRANCH_CODE_MAX = 64
BRANCH_SCOPE_MAX = 200


def normalize_branch_scope(role: Role, codes: list[str] | None) -> tuple[str, ...] | None:
    """S02: filial doirasi faqat Analyst/Viewer uchun; Owner/Admin barcha filiallarni ko‘radi."""
    if codes is None:
        return None
    if role in (Role.OWNER, Role.ADMIN):
        raise Forbidden(
            "Owner va Admin barcha filiallarni ko‘radi — doira faqat Analyst/Viewer uchun."
        )
    cleaned = tuple(dict.fromkeys(c.strip() for c in codes if c.strip()))
    if not cleaned:
        raise InvalidBranchScope(
            "Kamida bitta filial kodi kerak (barchasi uchun — bo‘sh qoldiring)."
        )
    if len(cleaned) > BRANCH_SCOPE_MAX or any(len(c) > BRANCH_CODE_MAX for c in cleaned):
        raise InvalidBranchScope("Filial kodlari juda ko‘p yoki juda uzun.")
    return cleaned


@dataclass(slots=True)
class Invitation:
    id: UUID
    tenant_id: UUID
    email: Email
    role: Role
    token_hash: str
    invited_by: UUID
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None

    def accept(self, now: datetime) -> None:
        if self.accepted_at is not None or now >= self.expires_at:
            raise InvitationInvalid("Taklif muddati o‘tgan yoki allaqachon ishlatilgan.")
        self.accepted_at = now


@dataclass(slots=True)
class PasswordResetToken:
    id: UUID
    user_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    def consume(self, now: datetime) -> None:
        if self.used_at is not None or now >= self.expires_at:
            raise ResetTokenInvalid("Havola muddati o‘tgan yoki allaqachon ishlatilgan.")
        self.used_at = now
