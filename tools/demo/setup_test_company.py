"""Test korxona: real integratsiyadagidek to‘liq sozlangan, faqat sintetik (soxta ERP/CRM) ma’lumot.

Foydalanuvchining akkauntiga alohida korxona qo‘shadi (asosiy korxonasi o‘zgarmaydi) va uni
foydalanuvchi o‘zi qiladigan qadamlar bilan to‘ldiradi — xuddi ilova orqali:
hisob qoidalarini tasdiqlash → ERP (4 obyekt) va CRM (bitimlar) ulash → mapping → sinxron.
Har qadam audit jurnaliga foydalanuvchi nomidan “demo-sozlash” belgisi bilan yoziladi.
Qayta ishga tushirilsa takrorlamaydi (idempotent): bor narsani o‘tkazib yuboradi.

Talab: `make stack` ishlab turgan bo‘lsin (worker’lar, soxta ERP :8070 va CRM :8071).

    cd services/business && uv run python ../../tools/demo/setup_test_company.py \\
        --email foydalanuvchi@misol.uz [--name "Test korxona"] [--dashboards]
"""

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from business.contexts.analytics.adapters.sql_store import SqlAnalyticsStore
from business.contexts.analytics.ports.store import MetricSettings
from business.contexts.analytics.public import SourceDatasets
from business.contexts.governance.public import SqlAuditLog
from business.contexts.identity.adapters.security import (
    Argon2PasswordHasher,
    FernetSecretBox,
    OpaqueSessionTokens,
    PyOtpTotpService,
)
from business.contexts.identity.adapters.sql import SqlIdentityUnitOfWorkFactory
from business.contexts.identity.application.service import IdentityService
from business.contexts.identity.domain.model import Email, Role
from business.contexts.integrations.adapters.sql import SqlIntegrationsStore
from business.contexts.integrations.application.sources import SourceService
from business.entrypoints.http.analytics import MetricSettingsIn
from business.kernel.clock import SystemClock
from business.platform.db import tenant_transaction
from business.platform.outbox import BoundOutbox

HERE = str(Path(__file__).resolve().parent)
DEFAULT_DB = "postgresql+asyncpg://business_app:business_app_dev@localhost:55432/business"
VIA = {"via": "demo-sozlash (tools/demo/setup_test_company.py)"}
SOURCES = [
    ("erp_api", "sales.order_line", "ERP: Sotuvlar"),
    ("erp_api", "sales.return", "ERP: Qaytarishlar"),
    ("erp_api", "inventory.movement", "ERP: Ombor harakatlari"),
    ("erp_api", "finance.receivable", "ERP: Debitorlik"),
    ("crm_api", "crm.deal", "CRM: Bitimlar (voronka)"),
]
SALES = {"posted": "confirmed", "draft": "draft", "cancelled": "cancelled"}
STATUS_MAPS: dict[str, dict[str, str]] = {
    "sales.order_line": SALES, "sales.return": SALES, "finance.receivable": {},
    "inventory.movement": {k: k for k in ("receipt", "sale", "return", "transfer_in",
                                          "transfer_out", "adjustment")},
    "crm.deal": {"open": "open", "won": "won", "lost": "lost"},
}


class _NoFiles:
    async def put(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("demo sozlash fayl yuklamaydi")


def log(message: str) -> None:
    print(f"· {message}", flush=True)


async def find_or_create_tenant(engine: AsyncEngine, email: str, name: str) -> tuple[UUID, UUID]:
    uow_factory = SqlIdentityUnitOfWorkFactory(engine)
    async with uow_factory() as uow:
        await uow.bind(tenant_id=None, user_id=None)
        user = await uow.users.get_by_email(Email(email))
        if user is None:
            raise SystemExit(f"Foydalanuvchi topilmadi: {email}")
        await uow.bind(tenant_id=None, user_id=user.id)
        memberships = await uow.memberships.list_for_user(user.id)
        tenants = {t.id: t for t in await uow.tenants.list_by_ids(
            [m.tenant_id for m in memberships])}
    for m in memberships:
        if m.role is Role.OWNER and tenants[m.tenant_id].name == name:
            log(f"“{name}” allaqachon bor — to‘ldiriladi")
            return m.tenant_id, user.id
    identity = IdentityService(
        uow_factory=uow_factory, hasher=Argon2PasswordHasher(), totp=PyOtpTotpService(),
        secret_box=FernetSecretBox(Fernet.generate_key().decode()),  # add_tenant ishlatmaydi
        tokens=OpaqueSessionTokens(), clock=SystemClock(), session_ttl=timedelta(hours=1))
    tenant_id = await identity.add_tenant(user.id, name)
    async with tenant_transaction(engine, tenant_id=tenant_id, user_id=user.id) as conn:
        await SqlAuditLog(conn, tenant_id).record(
            actor_id=user.id, actor_kind="user", action="tenant.created", target_type=None,
            target_id=None, details=VIA, ip=None)
    log(f"“{name}” korxonasi yaratildi ({email} — Owner)")
    return tenant_id, user.id


async def approve_rules(engine: AsyncEngine, tenant: UUID, user: UUID) -> None:
    async with tenant_transaction(engine, tenant_id=tenant, user_id=user) as conn:
        store = SqlAnalyticsStore(conn, tenant)
        if await store.metric_settings() is not None:
            return
        await store.save_metric_settings(MetricSettings(
            1, MetricSettingsIn().model_dump(), user, datetime.now(UTC)))
        await SqlAuditLog(conn, tenant).record(
            actor_id=user, actor_kind="user", action="metric_settings.approved",
            target_type=None, target_id=None, details={"version": 1, **VIA}, ip=None)
    log("hisob qoidalari tasdiqlandi (QQSsiz, qaytarish ayriladi, faqat tasdiqlangan hujjatlar)")


async def connect_sources(engine: AsyncEngine, tenant: UUID, user: UUID) -> None:
    def service(conn: Any) -> SourceService:
        return SourceService(SqlIntegrationsStore(conn, tenant), _NoFiles(),
                             BoundOutbox(conn, tenant), tenant)

    async with tenant_transaction(engine, tenant_id=tenant, user_id=user) as conn:
        existing = {(s["connector_id"], s["entity"]): s["id"]
                    for s in await SqlIntegrationsStore(conn, tenant).list_sources()}
    ids: dict[str, UUID] = {}
    for connector, entity, name in SOURCES:
        if (connector, entity) in existing:
            ids[entity] = existing[(connector, entity)]
            continue
        async with tenant_transaction(engine, tenant_id=tenant, user_id=user) as conn:
            ids[entity] = UUID((await service(conn).create(user, connector, name, None,
                                                           entity))["id"])
            await SqlAuditLog(conn, tenant).record(
                actor_id=user, actor_kind="user", action="integration.source_created",
                target_type="data_source", target_id=str(ids[entity]), details=VIA, ip=None)

    async def source(sid: UUID) -> dict[str, Any]:
        async with tenant_transaction(engine, tenant_id=tenant, user_id=user) as conn:
            found = await SqlIntegrationsStore(conn, tenant).get_source(sid)
        assert found is not None
        return found

    async def wait(sid: UUID, states: tuple[str, ...], what: str, seconds: int = 600) -> None:
        for _ in range(seconds * 2):
            s = await source(sid)
            if s["status"] == "failed" and "failed" not in states:
                raise SystemExit(f"{what}: {s['error_message']}")
            if s["status"] in states:
                return
            await asyncio.sleep(0.5)
        raise SystemExit(f"{what}: kutish tugadi — make stack ishlayaptimi?")

    for _, entity, name in SOURCES:
        sid = ids[entity]
        s = await source(sid)
        if s["status"] in ("discovering", "awaiting_mapping"):
            await wait(sid, ("awaiting_mapping",), f"{name}: tuzilma o‘qilmoqda")
            s = await source(sid)
            best = max((e for e in s["discovery"]["entities"] if e["entity"] == entity),
                       key=lambda e: e["match_score"])
            async with tenant_transaction(engine, tenant_id=tenant, user_id=user) as conn:
                await service(conn).approve_mapping(
                    user, sid, entity, best["suggested_mapping"],
                    [{"source_value": k, "canonical_value": v}
                     for k, v in STATUS_MAPS[entity].items()])
                await SqlAuditLog(conn, tenant).record(
                    actor_id=user, actor_kind="user", action="integration.mapping_approved",
                    target_type="data_source", target_id=str(sid),
                    details={"entity": entity, "match_score": best["match_score"], **VIA},
                    ip=None)
            log(f"{name}: mapping tasdiqlandi (moslik {best['match_score']:.0%})")
        await wait(sid, ("ready", "synced", "failed"), f"{name}: mapping")
        if (await source(sid))["status"] in ("ready", "failed"):
            async with tenant_transaction(engine, tenant_id=tenant, user_id=user) as conn:
                await service(conn).sync(user, sid)
        await wait(sid, ("synced",), f"{name}: sinxron")
        for _ in range(240):  # analitika yozuvlarni qabul qilguncha
            async with tenant_transaction(engine, tenant_id=tenant, user_id=user) as conn:
                usage = (await SourceDatasets(conn, tenant).status()).get(sid)
            if usage and usage[0]["is_active"]:
                break
            await asyncio.sleep(0.5)
        log(f"{name}: yuklandi va analitikada")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Test korxona")
    parser.add_argument("--dashboards", action="store_true",
                        help="tahlil dashboardlarini ham yaratish (tools/demo/dashboards.py)")
    args = parser.parse_args()
    engine = create_async_engine(os.environ.get("BUSINESS_DATABASE_URL", DEFAULT_DB))
    try:
        tenant, user = await find_or_create_tenant(engine, args.email, args.name)
        await approve_rules(engine, tenant, user)
        await connect_sources(engine, tenant, user)
        if args.dashboards:
            sys.path.insert(0, HERE)
            from dashboards import build_dashboards  # type: ignore[import-not-found]

            await build_dashboards(engine, tenant, user)
        log(f"tayyor: {args.name} (tenant {tenant})")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
