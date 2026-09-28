"""ERP REST API connector (`erp_api`): kursorli sahifalash bilan to‘liq o‘qish.

Shartnoma — docs/INTEGRATION_GUIDE.md, “Namunaviy ERP API”. Lokal/demo’da tools/fake_erp
shu shartnomani bajaradi; haqiqiy ERP uchun shu connector (yoki uning nusxasi) moslanadi.

Qoidalar:
- connector faqat o‘qiydi, qiymatlar xom satr sifatida beriladi (normallashtirish — Sync Engine);
- 429/5xx/tarmoq xatosi sahifa darajasida cheklangan qayta urinish, keyin `SourceUnavailable`
  (runner butun sinxronni keyinroq qaytaradi); 401/403/404/buzilgan javob — `InvalidSource`;
- kalit faqat Integration Runtime muhitida (`INTEGRATION_ERP_API_KEY`), logga yozilmaydi.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from typing import Any

import httpx

from ..ports.connector import (
    ConnectorManifest,
    DiscoveredSource,
    InvalidSource,
    RawRow,
    SourceHandle,
    SourceUnavailable,
)

RESOURCES = {
    "sales.order_line": "sales-invoice-lines",
    "sales.return": "sales-returns",
    "inventory.movement": "stock-movements",
    "finance.receivable": "receivables",
}
SAMPLE_ROWS = 5


def _cell(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        # JSON son sifatida kelgan pul: float xatosiz qisqa ko‘rinishi (repr) orqali.
        return str(Decimal(repr(value)))
    return str(value)


class ErpApiConnector:
    manifest = ConnectorManifest(
        connector_id="erp_api", version="1.0.0", display_name="ERP (REST API)",
        supported_entities=tuple(RESOURCES), capabilities=("full-sync",), is_demo=False,
        requires_object_ref=False,
    )

    def __init__(self, base_url: str, api_key: str, *, page_size: int = 500,
                 timeout: float = 30.0, attempts: int = 3,
                 transport: httpx.AsyncBaseTransport | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._page_size = page_size
        self._timeout = timeout
        self._attempts = attempts
        self._transport = transport
        self._sleep = sleep

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base, timeout=self._timeout,
                                 transport=self._transport,
                                 headers={"Authorization": f"Bearer {self._key}",
                                          "Accept": "application/json"})

    async def _get(self, client: httpx.AsyncClient, path: str,
                   params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(1, self._attempts + 1):
            try:
                r = await client.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt == self._attempts:
                    raise SourceUnavailable(f"ERP bilan aloqa yo‘q: {type(exc).__name__}") from exc
                await self._sleep(min(2.0 ** attempt, 30.0))
                continue
            if r.status_code in (429, 502, 503, 504) or r.status_code >= 500:
                if attempt == self._attempts:
                    raise SourceUnavailable(f"ERP javob bermayapti (HTTP {r.status_code})")
                retry_after = r.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 2.0 ** attempt
                await self._sleep(min(delay, 30.0))
                continue
            if r.status_code in (401, 403):
                raise InvalidSource("ERP kaliti noto‘g‘ri yoki ruxsat yo‘q (HTTP "
                                    f"{r.status_code}) — administrator kalitni tekshirsin")
            if r.status_code != 200:
                raise InvalidSource(f"ERP so‘rovi rad etildi: {path} (HTTP {r.status_code})")
            try:
                body = r.json()
            except ValueError as exc:
                raise InvalidSource("ERP javobi JSON emas") from exc
            if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                raise InvalidSource("ERP javobi kutilgan shaklda emas (`data` ro‘yxati yo‘q)")
            return body
        raise AssertionError("unreachable")

    async def discover_schema(self, source: SourceHandle) -> list[DiscoveredSource]:
        found = []
        async with self._client() as client:
            for resource in RESOURCES.values():
                body = await self._get(client, f"/api/v1/{resource}", {"limit": SAMPLE_ROWS})
                rows = [r for r in body["data"] if isinstance(r, dict)]
                if not rows:
                    continue  # bo‘sh resurs — mapping taklif qilib bo‘lmaydi
                columns = list(rows[0])
                found.append(DiscoveredSource(
                    f"erp://{resource}", columns,
                    [[_cell(r.get(c)) for c in columns] for r in rows]))
        if not found:
            raise InvalidSource("ERP’da o‘qiladigan ma’lumot topilmadi")
        return found

    async def read_rows(self, source: SourceHandle,
                        entity: str) -> AsyncIterator[tuple[int, RawRow]]:
        if entity not in RESOURCES:
            raise InvalidSource(f"erp_api {entity} ni qo‘llamaydi")
        path = f"/api/v1/{RESOURCES[entity]}"
        params: dict[str, Any] = {"limit": self._page_size}
        number = 0
        async with self._client() as client:
            while True:
                body = await self._get(client, path, params)
                for record in body["data"]:
                    number += 1
                    if not isinstance(record, dict):
                        raise InvalidSource(f"{number}-yozuv obyekt emas")
                    yield number, {str(k): _cell(v) for k, v in record.items()}
                cursor = body.get("next_cursor")
                if not cursor:
                    return
                params = {"limit": self._page_size, "cursor": cursor}
