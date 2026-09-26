import hashlib
import hmac
import logging
import secrets
from datetime import datetime

import pyotp
from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet

TOTP_ISSUER = "AI Business Office"


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._argon2 = _Argon2()

    def hash(self, password: str) -> str:
        return self._argon2.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._argon2.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False


class PyOtpTotpService:
    def new_secret(self) -> str:
        return pyotp.random_base32()

    def match_step(self, secret: str, code: str, now: datetime) -> int | None:
        # Soat farqi uchun ±1 qadam (30 soniya). Mos qadam replay himoyasi uchun qaytariladi.
        totp = pyotp.TOTP(secret)
        current = int(totp.timecode(now))
        candidate = code.strip()
        for step in (current - 1, current, current + 1):
            if hmac.compare_digest(totp.generate_otp(step), candidate):
                return step
        return None

    def provisioning_uri(self, secret: str, account: str) -> str:
        return str(pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=TOTP_ISSUER))


class FernetSecretBox:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()


class OpaqueSessionTokens:
    """Brauzerga tasodifiy token beriladi; DB’da faqat uning SHA-256 hash’i saqlanadi."""

    def new_token(self) -> str:
        return secrets.token_urlsafe(32)

    def hash(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


logger = logging.getLogger(__name__)


class LoggingNotifier:
    """Faqat lokal muhit uchun: havolani logga yozadi. Production email adapteri — alohida."""

    def __init__(self, web_base_url: str) -> None:
        self._base = web_base_url.rstrip("/")

    async def send_invitation(self, *, email: str, tenant_name: str, token: str) -> None:
        logger.warning("[local] %s uchun taklif (%s): %s/invite?token=%s",
                       email, tenant_name, self._base, token)

    async def send_password_reset(self, *, email: str, token: str) -> None:
        logger.warning("[local] %s uchun parol tiklash: %s/reset-password?token=%s",
                       email, self._base, token)


class DisabledNotifier:
    """Email kanali sozlanmagan muhit: token hech qayerga yozilmaydi."""

    async def send_invitation(self, *, email: str, tenant_name: str, token: str) -> None:
        logger.warning("Email kanali sozlanmagan: taklif yuborilmadi")

    async def send_password_reset(self, *, email: str, token: str) -> None:
        logger.warning("Email kanali sozlanmagan: parol tiklash havolasi yuborilmadi")
