from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    # DB/broker adapterlari qo‘shilganda ularning tekshiruvi shu yerga keladi.
    return {"status": "ok"}
