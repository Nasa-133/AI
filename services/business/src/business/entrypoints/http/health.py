from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .deps import ContainerDep

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(container: ContainerDep) -> JSONResponse:
    # Faqat Core vazifasi uchun zarur dependency tekshiriladi (TZ 13.13):
    # AI/Integration yoki OpenAI uzilishi Core’ni unready qilmaydi.
    try:
        async with container.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "db": "down"})
    return JSONResponse(content={"status": "ok", "db": "up"})
