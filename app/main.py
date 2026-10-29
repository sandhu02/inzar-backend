from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import RequestIdMiddleware, setup_logging
from app.db.session import check_db_health, engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    # Startup
    setup_logging(settings.LOG_LEVEL)
    yield
    # Shutdown
    await engine.dispose()


def create_app() -> FastAPI:
    setup_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title="Inzar API",
        description="Crowdsourced real-time local incident reporting platform backend",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error Handlers
    register_exception_handlers(app)

    # Health & Readiness Checks
    @app.get("/healthz", tags=["Health"], summary="Liveness check")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["Health"], summary="Readiness check")
    async def readyz(response: Response) -> dict[str, Any]:
        healthy, message = await check_db_health()
        if not healthy:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {
                "status": "unhealthy",
                "database": "unreachable",
                "error": message,
            }
        return {
            "status": "ready",
            "database": "healthy",
            "postgis": message,
        }

    # Mount API Routers
    app.include_router(api_v1_router)

    return app


app = create_app()
