from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from business.contexts.identity.domain.errors import (
    InvalidEmail,
    InvalidTenant,
    MfaAlreadyEnabled,
    MfaNotEnrolled,
    WeakPassword,
)
from business.contexts.identity.domain.model import (
    LOCKOUT_DURATION,
    MAX_FAILED_LOGINS,
    AuthSession,
    Email,
    Role,
    Tenant,
    User,
    validate_new_password,
)

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def make_user(**kw: object) -> User:
    return User(id=uuid4(), email=Email("a@b.uz"), password_hash="x", created_at=NOW, **kw)  # type: ignore[arg-type]


def test_email_is_normalized() -> None:
    assert Email("  Ali@Example.UZ ").value == "ali@example.uz"


@pytest.mark.parametrize("bad", ["", "no-at", "a@b", "a b@c.uz", "x" * 250 + "@a.uz"])
def test_email_rejects_invalid(bad: str) -> None:
    with pytest.raises(InvalidEmail):
        Email(bad)


def test_password_length_policy() -> None:
    with pytest.raises(WeakPassword):
        validate_new_password("short")
    validate_new_password("long-enough-password")


def test_tenant_validates_timezone_and_currency() -> None:
    Tenant(id=uuid4(), name="Demo MChJ", timezone="Asia/Tashkent", base_currency="UZS",
           created_at=NOW)
    with pytest.raises(InvalidTenant):
        Tenant(id=uuid4(), name="Demo", timezone="Mars/Base", base_currency="UZS", created_at=NOW)
    with pytest.raises(InvalidTenant):
        Tenant(id=uuid4(), name="Demo", timezone="Asia/Tashkent", base_currency="so'm",
               created_at=NOW)
    with pytest.raises(InvalidTenant):
        Tenant(id=uuid4(), name=" ", timezone="Asia/Tashkent", base_currency="UZS", created_at=NOW)


def test_user_locks_after_max_failed_logins_and_unlocks_after_duration() -> None:
    user = make_user()
    for _ in range(MAX_FAILED_LOGINS - 1):
        user.register_failed_login(NOW)
    assert not user.is_locked(NOW)
    user.register_failed_login(NOW)
    assert user.is_locked(NOW)
    assert not user.is_locked(NOW + LOCKOUT_DURATION + timedelta(seconds=1))


def test_successful_login_resets_counter() -> None:
    user = make_user()
    user.register_failed_login(NOW)
    user.register_successful_login()
    assert user.failed_login_count == 0


def test_mfa_enrollment_flow() -> None:
    user = make_user()
    with pytest.raises(MfaNotEnrolled):
        user.confirm_mfa()
    user.start_mfa_enrollment("enc")
    user.confirm_mfa()
    assert user.mfa_enabled
    with pytest.raises(MfaAlreadyEnabled):
        user.start_mfa_enrollment("enc2")


def test_mfa_reset_allows_new_enrollment() -> None:
    user = make_user()
    user.start_mfa_enrollment("enc")
    user.confirm_mfa()
    user.use_totp_step(10)
    user.reset_mfa()
    assert not user.mfa_enabled and user.mfa_secret_encrypted is None
    user.start_mfa_enrollment("enc2")
    user.confirm_mfa()
    user.use_totp_step(1)  # eski qadam hisobga olinmaydi


def test_secret_from_another_key_is_readable_error() -> None:
    from cryptography.fernet import Fernet

    from business.contexts.identity.adapters.security import FernetSecretBox
    from business.contexts.identity.domain.errors import MfaSecretUnreadable

    old = FernetSecretBox(Fernet.generate_key().decode()).encrypt("SECRET")
    with pytest.raises(MfaSecretUnreadable):
        FernetSecretBox(Fernet.generate_key().decode()).decrypt(old)


@pytest.mark.parametrize(
    ("role", "user_mfa", "verified", "expected"),
    [
        (Role.OWNER, False, False, False),
        (Role.OWNER, True, True, True),
        (Role.ADMIN, False, False, False),
        (Role.ANALYST, False, False, True),
        (Role.ANALYST, True, False, False),  # ixtiyoriy yoqilgan MFA ham majburiy bo‘ladi
        (Role.VIEWER, False, False, True),
    ],
)
def test_session_mfa_requirement(role: Role, user_mfa: bool, verified: bool,
                                 expected: bool) -> None:
    user = make_user(mfa_enabled=user_mfa)
    session = AuthSession(id=uuid4(), token_hash="h", user_id=user.id, tenant_id=uuid4(),
                          created_at=NOW, expires_at=NOW + timedelta(hours=1),
                          mfa_verified=verified)
    assert session.mfa_satisfied(user, role) is expected
