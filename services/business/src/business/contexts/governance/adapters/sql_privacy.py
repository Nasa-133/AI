"""Psevdonim tokenlari ombori: deterministik token (HMAC), asl qiymat Fernet bilan shifrlangan."""

import base64
import hashlib
import hmac
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.pii import TOKEN_RE


class SqlPiiVault:
    """Bitta vazifa uchun. `token_for`/`lookup` sinxron (domen funksiyalari uchun); DB bilan
    almashish `flush()` (yangi tokenlar) va `load()` (matndagi tokenlar) orqali."""

    def __init__(self, conn: AsyncConnection, tenant_id: UUID, task_id: UUID, key: str) -> None:
        self._c = conn
        self._t = tenant_id
        self._task = task_id
        self._fernet = Fernet(key.encode())
        self._hmac = hashlib.sha256(b"abo-pii-token:" + base64.urlsafe_b64decode(key)).digest()
        self._pending: dict[str, str] = {}
        self._known: dict[str, str] = {}

    def token_for(self, kind: str, value: str) -> str:
        digest = hmac.new(self._hmac, f"{self._task}|{kind}|{value}".encode(),
                          hashlib.sha256).hexdigest()[:8]
        token = f"[{kind}-{digest}]"
        if token not in self._known:
            self._pending[token] = value
            self._known[token] = value
        return token

    def lookup(self, token: str) -> str | None:
        return self._known.get(token)

    @property
    def masked_count(self) -> int:
        return len(self._known)

    async def flush(self) -> None:
        if not self._pending:
            return
        await self._c.execute(text(
            "INSERT INTO governance.pii_tokens (tenant_id, task_id, token, value_enc, created_at)"
            " VALUES (:t, :task, :token, :v, now()) ON CONFLICT DO NOTHING"),
            [{"t": self._t, "task": self._task, "token": k,
              "v": self._fernet.encrypt(v.encode()).decode()} for k, v in self._pending.items()])
        self._pending.clear()

    async def load(self, *texts: str) -> None:
        found = {m.group(0) for t in texts for m in TOKEN_RE.finditer(t)}
        tokens = sorted(found - set(self._known))
        if not tokens:
            return
        rows = (await self._c.execute(text(
            "SELECT token, value_enc FROM governance.pii_tokens WHERE task_id = :task"
            " AND token = ANY(:tokens)"), {"task": self._task, "tokens": tokens})).all()
        for r in rows:
            try:
                self._known[r.token] = self._fernet.decrypt(r.value_enc.encode()).decode()
            except InvalidToken:
                continue  # kalit almashgan — token o‘zgarmay qoladi (asl qiymat taxmin qilinmaydi)


class SqlPrivacySettings:
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        self._c = conn
        self._t = tenant_id

    async def get(self) -> tuple[bool, bool]:
        r = (await self._c.execute(text(
            "SELECT pseudonymize, mask_customer_names FROM governance.privacy_settings"))).first()
        return (True, True) if r is None else (bool(r.pseudonymize), bool(r.mask_customer_names))

    async def set(self, pseudonymize: bool, mask_customer_names: bool, *, user_id: UUID) -> None:
        await self._c.execute(text(
            "INSERT INTO governance.privacy_settings (tenant_id, pseudonymize,"
            " mask_customer_names, updated_by, updated_at) VALUES (:t, :p, :m, :u, now())"
            " ON CONFLICT (tenant_id) DO UPDATE SET pseudonymize = :p, mask_customer_names = :m,"
            " updated_by = :u, updated_at = now()"),
            {"t": self._t, "p": pseudonymize, "m": mask_customer_names, "u": user_id})

    async def purge_tokens(self, days: int) -> int:
        r = await self._c.execute(text(
            "DELETE FROM governance.pii_tokens WHERE created_at < now()"
            " - make_interval(days => :d)"), {"d": days})
        return int(r.rowcount or 0)
