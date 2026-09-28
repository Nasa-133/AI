"""FastAPI ilovasi. Ishga tushirish: `uvicorn business.bootstrap.app:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from business.contexts.identity.ports.security import IdentityNotifier
from business.entrypoints.http import (
    analytics,
    dashboards,
    documents,
    governance,
    health,
    identity,
    integrations,
    members,
    workspace,
)
from business.entrypoints.http.errors import install_error_handlers
from business.entrypoints.http.security import install_middlewares
from business.entrypoints.internal import tools

from .container import build_container
from .settings import Settings


def create_app(
    settings: Settings | None = None, *, notifier: IdentityNotifier | None = None
) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    container = build_container(settings, notifier=notifier)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await container.engine.dispose()
        close = getattr(container.rate_limiter, "close", None)
        if close is not None:
            await close()

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
    app.include_router(members.router)
    app.include_router(workspace.router)
    app.include_router(analytics.router)
    app.include_router(dashboards.router)
    app.include_router(documents.router)
    app.include_router(integrations.router)
    app.include_router(governance.router)
    app.include_router(tools.router)
    return app
