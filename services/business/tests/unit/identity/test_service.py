from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from business.contexts.identity.application.dto import Login, OnboardTenant
from business.contexts.identity.application.errors import (
    AccountLocked,
    EmailTaken,
    InvalidCredentials,
    InvalidMfaCode,
    NotAMember,
    Unauthenticated,
)
from business.contexts.identity.application.service import IdentityService
from business.contexts.identity.domain.model import MAX_FAILED_LOGINS, Membership, Role
from business.kernel.errors import BusinessError

from .fakes import (
    FakeClock,
    FakeHasher,
    FakeSecretBox,
    FakeTokens,
    FakeTotp,
    FakeUnitOfWork,
    Store,
)

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
PASSWORD = "correct-horse-battery"


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def service(store: Store, clock: FakeClock) -> IdentityService:
    return IdentityService(
        uow_factory=lambda: FakeUnitOfWork(store),
        hasher=FakeHasher(),
        totp=FakeTotp(),
        secret_box=FakeSecretBox(),
        tokens=FakeTokens(),
        clock=clock,
        session_ttl=timedelta(hours=12),
    )


async def onboard(service: IdentityService, email: str = "owner@demo.uz",
                  name: str = "Demo MChJ"):  # type: ignore[no-untyped-def]
    return await service.onboard_tenant(OnboardTenant(email=email, password=PASSWORD,
                                                      tenant_name=name))


async def test_onboarding_creates_owner_that_must_complete_mfa(service: IdentityService) -> None:
    issued = await onboard(service)
    assert issued.context.role is Role.OWNER
    assert issued.context.mfa_satisfied is False
    ctx = await service.authenticate(issued.token)
    assert ctx.tenant_id == issued.context.tenant_id


async def test_onboarding_rejects_duplicate_email(service: IdentityService) -> None:
    await onboard(service)
    with pytest.raises(EmailTaken):
        await onboard(service, email="OWNER@demo.uz")


async def test_mfa_enroll_and_verify_satisfies_session(service: IdentityService) -> None:
    issued = await onboard(service)
    enrollment = await service.enroll_mfa(issued.context)
    assert enrollment.provisioning_uri.startswith("otpauth://")
    with pytest.raises(InvalidMfaCode):
        await service.verify_mfa(issued.context, "000000")
    await service.verify_mfa(issued.context, FakeTotp.code_at(NOW))
    ctx = await service.authenticate(issued.token)
    assert ctx.mfa_satisfied


async def test_new_login_requires_mfa_again(service: IdentityService) -> None:
    issued = await onboard(service)
    await service.enroll_mfa(issued.context)
    await service.verify_mfa(issued.context, FakeTotp.code_at(NOW))
    again = await service.login(Login(email="owner@demo.uz", password=PASSWORD))
    assert again.context.mfa_satisfied is False


async def test_totp_code_cannot_be_reused(service: IdentityService, clock: FakeClock) -> None:
    issued = await onboard(service)
    await service.enroll_mfa(issued.context)
    await service.verify_mfa(issued.context, FakeTotp.code_at(NOW))
    again = await service.login(Login(email="owner@demo.uz", password=PASSWORD))
    with pytest.raises(BusinessError) as reused:
        await service.verify_mfa(again.context, FakeTotp.code_at(NOW))
    assert reused.value.code == "INVALID_MFA_CODE"
    clock.current = NOW + timedelta(seconds=30)
    await service.verify_mfa(again.context, FakeTotp.code_at(clock.current))


async def test_wrong_password_is_generic_and_counts(service: IdentityService,
                                                    store: Store) -> None:
    await onboard(service)
    with pytest.raises(InvalidCredentials):
        await service.login(Login(email="owner@demo.uz", password="wrong-password"))
    with pytest.raises(InvalidCredentials):
        await service.login(Login(email="nobody@demo.uz", password="wrong-password"))
    (user,) = store.users.values()
    assert user.failed_login_count == 1  # muvaffaqiyatsiz urinish commit qilinadi


async def test_lockout_blocks_even_correct_password(service: IdentityService,
                                                    clock: FakeClock) -> None:
    await onboard(service)
    for _ in range(MAX_FAILED_LOGINS):
        with pytest.raises(InvalidCredentials):
            await service.login(Login(email="owner@demo.uz", password="wrong-password"))
    with pytest.raises(AccountLocked):
        await service.login(Login(email="owner@demo.uz", password=PASSWORD))
    clock.current = NOW + timedelta(minutes=16)
    assert (await service.login(Login(email="owner@demo.uz", password=PASSWORD))).token


async def test_expired_session_is_rejected(service: IdentityService, clock: FakeClock) -> None:
    issued = await onboard(service)
    clock.current = NOW + timedelta(hours=13)
    with pytest.raises(Unauthenticated):
        await service.authenticate(issued.token)


async def test_logout_invalidates_session(service: IdentityService) -> None:
    issued = await onboard(service)
    await service.logout(issued.token)
    with pytest.raises(Unauthenticated):
        await service.authenticate(issued.token)


async def test_revoked_membership_invalidates_session(service: IdentityService,
                                                      store: Store) -> None:
    issued = await onboard(service)
    store.memberships.clear()
    with pytest.raises(Unauthenticated):
        await service.authenticate(issued.token)


async def test_switch_tenant_requires_membership_and_rotates_session(
    service: IdentityService, store: Store
) -> None:
    first = await onboard(service)
    other = await onboard(service, email="other@demo.uz", name="Boshqa MChJ")
    with pytest.raises(NotAMember):
        await service.switch_tenant(first.context, other.context.tenant_id)

    # Birinchi foydalanuvchini ikkinchi korxonaga analitik sifatida qo‘shamiz.
    m = Membership(id=uuid4(), tenant_id=other.context.tenant_id, user_id=first.context.user_id,
                   role=Role.ANALYST, created_at=NOW)
    store.memberships[m.id] = m
    switched = await service.switch_tenant(first.context, other.context.tenant_id)
    assert switched.context.tenant_id == other.context.tenant_id
    assert switched.context.role is Role.ANALYST
    with pytest.raises(Unauthenticated):
        await service.authenticate(first.token)

    me = await service.get_me(switched.context)
    assert {x.tenant_name for x in me.memberships} == {"Demo MChJ", "Boshqa MChJ"}
