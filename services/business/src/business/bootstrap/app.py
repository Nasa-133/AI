"""FastAPI ilovasi. Ishga tushirish: `uvicorn business.bootstrap.app:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from business.entrypoints.http import health, identity
from business.entrypoints.http.errors import install_error_handlers
from business.entrypoints.http.security import install_middlewares

from .container import build_container
from .settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    container = build_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await container.engine.dispose()

    app = FastAPI(
        title="AI Business Office — Business API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.environment == "local" else None,
        openapi_url="/api/openapi.json",
    )
    app.state.container = container
    install_error_handlers(app)
    install_middlewares(app)
    app.include_router(health.router)
    app.include_router(identity.router)
    return app
