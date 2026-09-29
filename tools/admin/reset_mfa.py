"""Foydalanuvchi 2FA’sini tiklash (autentifikator yo‘qolgan yoki shifrlash kaliti almashgan).

Parol o‘zgarmaydi. Keyingi kirishda foydalanuvchi QR-kodni qaytadan skanerlab 2FA’ni sozlaydi.
Har korxonasining audit jurnaliga yoziladi.

    cd services/business && uv run python ../../tools/admin/reset_mfa.py --email ism@misol.uz
"""

import argparse
import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine

from business.contexts.governance.public import SqlAuditLog
from business.contexts.identity.adapters.sql import SqlIdentityUnitOfWorkFactory
from business.contexts.identity.domain.model import Email
from business.platform.db import tenant_transaction

DEFAULT_DB = "postgresql+asyncpg://business_app:business_app_dev@localhost:55432/business"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    engine = create_async_engine(os.environ.get("BUSINESS_DATABASE_URL", DEFAULT_DB))
    try:
        async with SqlIdentityUnitOfWorkFactory(engine)() as uow:
            await uow.bind(tenant_id=None, user_id=None)
            user = await uow.users.get_by_email(Email(args.email))
            if user is None:
                raise SystemExit(f"Foydalanuvchi topilmadi: {args.email}")
            await uow.bind(tenant_id=None, user_id=user.id)
            user.reset_mfa()
            await uow.users.save(user)
            tenants = [m.tenant_id for m in await uow.memberships.list_for_user(user.id)]
            await uow.commit()
        for tenant in tenants:
            async with tenant_transaction(engine, tenant_id=tenant, user_id=user.id) as conn:
                await SqlAuditLog(conn, tenant).record(
                    actor_id=None, actor_kind="system", action="identity.mfa_reset",
                    target_type="user", target_id=str(user.id),
                    details={"via": "tools/admin/reset_mfa.py"}, ip=None)
        print(f"· 2FA tiklandi: {args.email}. Keyingi kirishda QR-kodni qayta skanerlang.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
