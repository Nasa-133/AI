"""Soxta ERP REST API — haqiqiy ERP ulanishini mashq qilish va demo uchun (sintetik ma’lumot).

Ishga tushirish (repo ildizidan):
    make fake-erp                       # yoki:
    cd services/integration_runtime && uv run python ../../tools/fake_erp/app.py --port 8070

API (docs/INTEGRATION_GUIDE.md dagi “namunaviy ERP API” shartnomasi):
    GET  /api/v1/health                               (kalitsiz)
    GET  /api/v1/{resource}?limit=&cursor=&updated_since=
         resource: sales-invoice-lines | sales-returns | stock-movements | receivables
         javob: {"data": [...], "next_cursor": str|null, "as_of": iso, "total": int}
    POST /admin/outage?seconds=60                     (uzilishni simulyatsiya qilish)
    GET  /admin/stats

Autentifikatsiya: `Authorization: Bearer <FAKE_ERP_API_KEY>` (standart: fake-erp-dev-key).
Kursor sahifalash davomida bir xil `as_of` holatini saqlaydi — sinxron o‘rtasida yangi hujjat
qo‘shilsa ham sahifalar siljimaydi (to‘liq snapshot izchil).
"""

import argparse
import base64
import hmac
import json
import os
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

try:  # modul sifatida (testlar) ham, skript sifatida ham ishlaydi
    from .erp import RESOURCES, ErpData, filter_since, page
except ImportError:  # pragma: no cover
    from erp import RESOURCES, ErpData, filter_since, page  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT / "fixtures/synthetic/demo"
MAX_LIMIT = 1000


def _encode(offset: int, as_of: datetime, since: str | None) -> str:
    raw = json.dumps({"o": offset, "t": as_of.isoformat(), "s": since}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(cursor: str) -> tuple[int, datetime, str | None]:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        return int(raw["o"]), datetime.fromisoformat(raw["t"]), raw.get("s")
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, {"code": "BAD_CURSOR", "message": "Kursor noto‘g‘ri"}) from exc


Records = Callable[[str, datetime], list[dict[str, str | None]]]


def create_app(*, data: ErpData | None = None, api_key: str | None = None,
               clock: Callable[[], datetime] | None = None, fail_rate: float = 0.0) -> FastAPI:
    erp = data or ErpData.load(DEMO_DIR)
    return create_rest_app(
        title="Soxta Savdo ERP (demo)", system="ERP", resources=RESOURCES,
        records=erp.records, api_key=api_key or os.environ.get("FAKE_ERP_API_KEY",
                                                              "fake-erp-dev-key"),
        clock=clock, fail_rate=fail_rate)


def create_rest_app(*, title: str, system: str, resources: tuple[str, ...], records: Records,
                    api_key: str, clock: Callable[[], datetime] | None = None,
                    fail_rate: float = 0.0) -> FastAPI:
    """Namunaviy tashqi tizim API’si (ERP, CRM): Bearer kalit, izchil kursor, nosozliklar."""
    key = api_key
    now = clock or (lambda: datetime.now(UTC))
    state: dict[str, Any] = {"outage_until": None}
    rng = random.Random(7)  # noqa: S311 — nosozlik simulyatsiyasi, kriptografiya emas
    app = FastAPI(title=title, version="1.0.0")

    def authorize(authorization: str | None) -> None:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(token.encode(), key.encode()):
            raise HTTPException(401, {"code": "UNAUTHORIZED", "message": "API kaliti noto‘g‘ri"})

    def available() -> None:
        until = state["outage_until"]
        if until is not None and now() < until:
            raise HTTPException(503, {"code": "MAINTENANCE",
                                      "message": f"{system} texnik ishlarda"},
                                headers={"Retry-After": "5"})
        if fail_rate and rng.random() < fail_rate:
            raise HTTPException(429, {"code": "RATE_LIMITED", "message": "Juda ko‘p so‘rov"},
                                headers={"Retry-After": "1"})

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "system": title, "version": "1.0.0"}

    @app.get("/api/v1/{resource}")
    async def listing(resource: str,
                      authorization: Annotated[str | None, Header()] = None,
                      limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 500,
                      cursor: str | None = None,
                      updated_since: str | None = None) -> dict[str, Any]:
        authorize(authorization)
        if resource not in resources:
            raise HTTPException(404, {"code": "NOT_FOUND", "message": f"Resurs yo‘q: {resource}"})
        available()
        if cursor:
            offset, as_of, since = _decode(cursor)
        else:
            offset, as_of, since = 0, now(), updated_since
            if since:
                try:
                    datetime.fromisoformat(since)
                except ValueError as exc:
                    raise HTTPException(400, {"code": "BAD_REQUEST",
                                              "message": "updated_since ISO 8601 bo‘lsin"}) from exc
        rows = filter_since(records(resource, as_of), since)
        chunk, nxt = page(rows, offset, limit)
        return {"data": chunk, "next_cursor": _encode(nxt, as_of, since) if nxt else None,
                "as_of": as_of.isoformat(), "total": len(rows)}

    @app.post("/admin/outage")
    async def outage(authorization: Annotated[str | None, Header()] = None,
                     seconds: Annotated[int, Query(ge=0, le=3600)] = 60) -> dict[str, Any]:
        authorize(authorization)
        state["outage_until"] = now() + timedelta(seconds=seconds) if seconds else None
        return {"outage_until": state["outage_until"].isoformat() if seconds else None}

    @app.get("/admin/stats")
    async def admin_stats(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        authorize(authorization)
        return {"as_of": now().isoformat(),
                "records": {r: len(records(r, now())) for r in resources}}

    @app.exception_handler(HTTPException)
    async def error(_: Any, exc: HTTPException) -> JSONResponse:
        body = exc.detail if isinstance(exc.detail, dict) else {"code": "ERROR",
                                                                "message": str(exc.detail)}
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Soxta ERP REST API (demo)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("FAKE_ERP_PORT", "8070")))
    parser.add_argument("--fail-rate", type=float,
                        default=float(os.environ.get("FAKE_ERP_FAIL_RATE", "0")))
    args = parser.parse_args()
    uvicorn.run(create_app(fail_rate=args.fail_rate), host="127.0.0.1", port=args.port,
                log_level="info")


if __name__ == "__main__":
    main()
