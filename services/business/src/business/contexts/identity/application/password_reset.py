import logging
from uuid import uuid4

from business.kernel.clock import Clock

from ..domain.errors import ResetTokenInvalid
from ..domain.model import PASSWORD_RESET_TTL, Email, PasswordResetToken, validate_new_password
from ..ports.repositories import IdentityUnitOfWorkFactory
from ..ports.security import IdentityNotifier, PasswordHasher, SessionTokens

logger = logging.getLogger(__name__)


class PasswordResetService:
    def __init__(
        self,
        *,
        uow_factory: IdentityUnitOfWorkFactory,
        hasher: PasswordHasher,
        tokens: SessionTokens,
        notifier: IdentityNotifier,
        clock: Clock,
    ) -> None:
        self._uow = uow_factory
        self._hasher = hasher
        self._tokens = tokens
        self._notifier = notifier
        self._clock = clock

    async def request(self, email: str) -> None:
        """Email mavjud-mavjud emasligi javobdan bilinmaydi."""
        address = Email(email)
        now = self._clock.now()
        token = self._tokens.new_token()
        async with self._uow() as uow:
            user = await uow.users.get_by_email(address)
            if user is None:
                return
            await uow.password_resets.add(PasswordResetToken(
                id=uuid4(), user_id=user.id, token_hash=self._tokens.hash(token),
                created_at=now, expires_at=now + PASSWORD_RESET_TTL,
            ))
            await uow.commit()
        try:
            await self._notifier.send_password_reset(email=address.value, token=token)
        except Exception:
            logger.exception("Parol tiklash havolasini yuborib bo‘lmadi")

    async def confirm(self, token: str, new_password: str) -> None:
        validate_new_password(new_password)
        now = self._clock.now()
        async with self._uow() as uow:
            reset = await uow.password_resets.get_by_token_hash(self._tokens.hash(token))
            if reset is None:
                raise ResetTokenInvalid("Havola muddati o‘tgan yoki allaqachon ishlatilgan.")
            reset.consume(now)
            user = await uow.users.get(reset.user_id)
            if user is None:
                raise ResetTokenInvalid("Havola muddati o‘tgan yoki allaqachon ishlatilgan.")
            user.change_password(self._hasher.hash(new_password))
            await uow.users.save(user)
            await uow.password_resets.save(reset)
            # Parol almashsa barcha ochiq sessiyalar yopiladi.
            await uow.sessions.delete_for_user(user.id)
            await uow.commit()
