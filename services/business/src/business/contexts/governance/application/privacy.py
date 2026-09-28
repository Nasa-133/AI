"""Psevdonimlash xizmati: AI’ga ketadigan matn/natijani yashirish, qaytganini tiklash."""

from typing import Any, Protocol

from business.kernel.errors import BusinessError

from ..domain.pii import mask_text, mask_value, unmask_text, unmask_value


class PrivacyForbidden(BusinessError):
    code = "FORBIDDEN"


class Vault(Protocol):
    def token_for(self, kind: str, value: str) -> str: ...
    def lookup(self, token: str) -> str | None: ...
    async def flush(self) -> None: ...
    async def load(self, *texts: str) -> None: ...


class PrivacySettingsStore(Protocol):
    async def get(self) -> tuple[bool, bool]: ...
    async def set(self, pseudonymize: bool, mask_customer_names: bool, *,
                  user_id: Any) -> None: ...


class TaskPrivacy:
    """Bitta vazifa doirasida (tokenlar vazifaga bog‘langan)."""

    def __init__(self, vault: Vault, *, enabled: bool, mask_people: bool) -> None:
        self._v = vault
        self._enabled = enabled
        self._people = mask_people

    async def mask_text(self, text: str) -> str:
        if not self._enabled:
            return text
        masked = mask_text(text, self._v.token_for)
        await self._v.flush()
        return masked

    async def mask_data(self, data: Any) -> Any:
        if not self._enabled:
            return data
        masked = mask_value(data, self._v.token_for, mask_people=self._people)
        await self._v.flush()
        return masked

    async def unmask_text(self, text: str) -> str:
        await self._v.load(text)
        return unmask_text(text, self._v.lookup)

    async def unmask_data(self, data: Any) -> Any:
        await self._v.load(str(data))
        return unmask_value(data, self._v.lookup)


async def privacy_overview(store: PrivacySettingsStore) -> dict[str, bool]:
    pseudonymize, people = await store.get()
    return {"pseudonymize": pseudonymize, "mask_customer_names": people}


async def update_privacy(store: PrivacySettingsStore, role: str, user_id: Any,
                         pseudonymize: bool, mask_customer_names: bool) -> dict[str, bool]:
    if role != "owner":
        raise PrivacyForbidden("Maxfiylik sozlamasini faqat korxona egasi o‘zgartiradi.")
    await store.set(pseudonymize, mask_customer_names, user_id=user_id)
    return await privacy_overview(store)
