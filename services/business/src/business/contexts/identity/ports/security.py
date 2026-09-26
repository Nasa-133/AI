from datetime import datetime
from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password_hash: str, password: str) -> bool: ...


class TotpService(Protocol):
    def new_secret(self) -> str: ...

    def match_step(self, secret: str, code: str, now: datetime) -> int | None:
        """Kod mos kelgan vaqt qadami (replay himoyasi uchun) yoki None."""
        ...

    def provisioning_uri(self, secret: str, account: str) -> str: ...


class SecretBox(Protocol):
    """Saqlanadigan maxfiy qiymatlarni (masalan, TOTP secret) shifrlash."""

    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, ciphertext: str) -> str: ...


class SessionTokens(Protocol):
    """Sessiya, taklif va parol tiklash uchun tasodifiy token; DB’da faqat hash."""

    def new_token(self) -> str: ...
    def hash(self, token: str) -> str: ...


class IdentityNotifier(Protocol):
    """Foydalanuvchiga havola yuborish kanali (email). Token faqat shu kanal orqali ketadi."""

    async def send_invitation(self, *, email: str, tenant_name: str, token: str) -> None: ...
    async def send_password_reset(self, *, email: str, token: str) -> None: ...
