"""Delegated capability token (docs/design/stage1.md §6): `v1.<payload>.<hmac>`.

AI Runtime uchun shaffof emas. Faqat Core imzolaydi va tekshiradi. Token vakolat
**dalili emas**: har chaqiriqda a’zolik va rol DB’dan qayta tekshiriladi.
"""

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from business.kernel.errors import BusinessError


class InvalidCapability(BusinessError):
    code = "INVALID_CAPABILITY"


@dataclass(frozen=True, slots=True)
class Capability:
    task_id: UUID
    tenant_id: UUID
    user_id: UUID
    role_key: str
    tools: tuple[str, ...]
    expires_at: datetime


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class CapabilitySigner:
    def __init__(self, key: str) -> None:
        if len(key) < 32:
            raise ValueError("Capability imzo kaliti kamida 32 belgi bo‘lishi kerak.")
        self._key = key.encode()

    def _mac(self, payload: str) -> str:
        return _b64(hmac.new(self._key, payload.encode(), hashlib.sha256).digest())

    def issue(self, cap: Capability) -> str:
        payload = _b64(json.dumps({
            "task_id": str(cap.task_id), "tenant_id": str(cap.tenant_id),
            "user_id": str(cap.user_id), "role_key": cap.role_key, "tools": list(cap.tools),
            "exp": int(cap.expires_at.timestamp()),
        }, separators=(",", ":")).encode())
        return f"v1.{payload}.{self._mac(payload)}"

    def verify(self, token: str, now: datetime) -> Capability:
        try:
            version, payload, mac = token.split(".")
        except ValueError:
            raise InvalidCapability("Capability formati noto‘g‘ri.") from None
        if version != "v1" or not hmac.compare_digest(mac, self._mac(payload)):
            raise InvalidCapability("Capability imzosi noto‘g‘ri.")
        data = json.loads(_unb64(payload))
        cap = Capability(UUID(data["task_id"]), UUID(data["tenant_id"]), UUID(data["user_id"]),
                         data["role_key"], tuple(data["tools"]),
                         datetime.fromtimestamp(data["exp"], tz=now.tzinfo))
        if now >= cap.expires_at:
            raise InvalidCapability("Capability muddati tugagan.")
        return cap
