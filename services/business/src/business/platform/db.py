"""Business Core ichidagi DB infratuzilmasi: engine va tenant kontekstini bog‘lash."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


async def bind_request_context(
    conn: AsyncConnection, *, tenant_id: UUID | None, user_id: UUID | None
) -> None:
    """RLS uchun kontekstni faqat joriy tranzaksiyaga o‘rnatadi.

    `set_config(..., true)` tranzaksiya tugashi bilan tozalanadi, shuning uchun
    connection pool orqali boshqa so‘rovga sizib chiqmaydi.
    """
    await conn.execute(
        text(
            "SELECT set_config('app.tenant_id', :tenant_id, true),"
            " set_config('app.user_id', :user_id, true)"
        ),
        {
            "tenant_id": str(tenant_id) if tenant_id else "",
            "user_id": str(user_id) if user_id else "",
        },
    )
