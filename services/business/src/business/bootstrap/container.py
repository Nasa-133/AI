"""Composition root: concrete adapterlar shu yerda use-case’larga ulanadi."""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from business.contexts.identity.adapters.security import (
    Argon2PasswordHasher,
    FernetSecretBox,
    OpaqueSessionTokens,
    PyOtpTotpService,
)
from business.contexts.identity.adapters.sql import SqlIdentityUnitOfWorkFactory
from business.contexts.identity.application.service import IdentityService
from business.kernel.clock import SystemClock
from business.platform.db import make_engine

from .settings import Settings


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    identity: IdentityService


def build_container(settings: Settings) -> Container:
    engine = make_engine(settings.database_url)
    identity = IdentityService(
        uow_factory=SqlIdentityUnitOfWorkFactory(engine),
        hasher=Argon2PasswordHasher(),
        totp=PyOtpTotpService(),
        secret_box=FernetSecretBox(settings.data_encryption_key),
        tokens=OpaqueSessionTokens(),
        clock=SystemClock(),
        session_ttl=timedelta(hours=settings.session_ttl_hours),
    )
    return Container(settings=settings, engine=engine, identity=identity)
