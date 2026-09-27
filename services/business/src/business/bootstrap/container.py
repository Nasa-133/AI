"""Composition root: concrete adapterlar shu yerda use-case’larga ulanadi."""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from business.contexts.identity.adapters.security import (
    Argon2PasswordHasher,
    DisabledNotifier,
    FernetSecretBox,
    LoggingNotifier,
    OpaqueSessionTokens,
    PyOtpTotpService,
)
from business.contexts.identity.adapters.sql import SqlIdentityUnitOfWorkFactory
from business.contexts.identity.application.members import MembershipService
from business.contexts.identity.application.password_reset import PasswordResetService
from business.contexts.identity.application.service import IdentityService
from business.contexts.identity.application.sessions import SessionIssuer
from business.contexts.identity.ports.security import IdentityNotifier
from business.kernel.clock import SystemClock
from business.kernel.rate_limit import RateLimiter
from business.platform.capability import CapabilitySigner
from business.platform.db import make_engine
from business.platform.rate_limit import NoopRateLimiter, RedisRateLimiter
from business.platform.storage import S3ObjectStorage

from .settings import Settings


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    identity: IdentityService
    members: MembershipService
    password_reset: PasswordResetService
    rate_limiter: RateLimiter
    capabilities: CapabilitySigner
    storage: S3ObjectStorage


def build_container(settings: Settings, *, notifier: IdentityNotifier | None = None) -> Container:
    engine = make_engine(settings.database_url)
    uow_factory = SqlIdentityUnitOfWorkFactory(engine)
    hasher = Argon2PasswordHasher()
    tokens = OpaqueSessionTokens()
    clock = SystemClock()
    session_ttl = timedelta(hours=settings.session_ttl_hours)
    if notifier is None:
        notifier = (LoggingNotifier(settings.web_base_url) if settings.notifier == "log"
                    else DisabledNotifier())

    identity = IdentityService(
        uow_factory=uow_factory,
        hasher=hasher,
        totp=PyOtpTotpService(),
        secret_box=FernetSecretBox(settings.data_encryption_key),
        tokens=tokens,
        clock=clock,
        session_ttl=session_ttl,
    )
    members = MembershipService(
        uow_factory=uow_factory,
        hasher=hasher,
        tokens=tokens,
        notifier=notifier,
        clock=clock,
        sessions=SessionIssuer(tokens=tokens, clock=clock, ttl=session_ttl),
    )
    password_reset = PasswordResetService(
        uow_factory=uow_factory, hasher=hasher, tokens=tokens, notifier=notifier, clock=clock
    )
    rate_limiter: RateLimiter = (RedisRateLimiter(settings.redis_url) if settings.redis_url
                                 else NoopRateLimiter())
    storage = S3ObjectStorage(endpoint_url=settings.s3_endpoint_url,
                              access_key=settings.s3_access_key,
                              secret_key=settings.s3_secret_key, region=settings.s3_region)
    return Container(settings=settings, engine=engine, identity=identity, members=members,
                     password_reset=password_reset, rate_limiter=rate_limiter,
                     capabilities=CapabilitySigner(settings.capability_signing_key),
                     storage=storage)
