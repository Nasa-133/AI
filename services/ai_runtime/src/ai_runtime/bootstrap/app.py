"""Ishga tushirish: `uvicorn ai_runtime.bootstrap.app:create_app --factory`."""

from fastapi import FastAPI

from ai_runtime.entrypoints import embed, http

from .container import make_embedder
from .settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    # Ichki servis: brauzerga ochilmaydi, docs faqat lokal muhitda.
    app = FastAPI(
        title="AI Business Office — AI Runtime",
        version="0.1.0",
        docs_url="/docs" if settings.environment == "local" else None,
    )
    # Core bilan umumiy servis tokeni (Core → AI embed, AI → Core Tool API).
    app.state.service_token = settings.business_tools_token
    app.state.embedder = make_embedder(settings)
    app.include_router(http.router)
    app.include_router(embed.router)
    return app
