import hashlib
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

    def verify(self, secret: str, code: str, now: datetime) -> bool:
        # Soat farqi uchun ±1 oyna (30 soniya).
        return bool(pyotp.TOTP(secret).verify(code.strip(), for_time=now, valid_window=1))

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
