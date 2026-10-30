import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import RequestIdMiddleware, setup_logging
from app.db.session import check_db_health, engine


class ResponseEnvelopeMiddleware(BaseHTTPMiddleware):
    """
    Interceptor ensuring uniform response structure across all /api/ endpoints:
    {
        "status": true | false,
        "success": true | false,
        "status_code": int,
        "message": str (on error or info),
        "data": ... (payload on success, null on error),
        "error": { "code": "...", "message": "...", "details": {} } (on error)
    }
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Pass through docs, openapi, and system health checks without modification
        if not request.url.path.startswith("/api/"):
            res: Response = await call_next(request)
            return res

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            logging.getLogger("inzar.errors").exception(
                "Unhandled exception in request dispatch: %s", exc
            )
            err_str = str(exc)
            if "does not exist" in err_str or "UndefinedTableError" in err_str:
                msg = (
                    "Database table or relation does not exist. "
                    "Please run database migrations (`uv run alembic upgrade head`)."
                )
                code = "database_migration_required"
            else:
                msg = "An unexpected server error occurred"
                code = "internal_server_error"

            content = {
                "status": False,
                "success": False,
                "status_code": 500,
                "message": msg,
                "error": {
                    "code": code,
                    "message": msg,
                    "details": {},
                },
                "data": None,
            }
            return JSONResponse(status_code=500, content=content)

        # Do not modify HTTP 204 No Content
        if response.status_code == 204:
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Consume response body
        if isinstance(response, StreamingResponse):
            raw_chunks: list[bytes] = []
            async for chunk in response.body_iterator:
                if isinstance(chunk, bytes):
                    raw_chunks.append(chunk)
                elif isinstance(chunk, str):
                    raw_chunks.append(chunk.encode("utf-8"))
                else:
                    raw_chunks.append(bytes(chunk))
            body_bytes = b"".join(raw_chunks)
        else:
            body_bytes = bytes(getattr(response, "body", b""))

        if not body_bytes:
            return response

        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # Do not double-envelope if response already adheres to standard shape
        if isinstance(body, dict) and "status" in body and "status_code" in body and "data" in body:
            new_content = body_bytes
        else:
            is_success = response.status_code < 400
            if is_success:
                enveloped: dict[str, Any] = {
                    "status": True,
                    "success": True,
                    "status_code": response.status_code,
                    "data": body,
                }
            else:
                error_obj = body.get("error", {}) if isinstance(body, dict) else {}
                code = error_obj.get("code", "error") if isinstance(error_obj, dict) else "error"
                msg = (
                    (error_obj.get("message") if isinstance(error_obj, dict) else None)
                    or (body.get("message") if isinstance(body, dict) else None)
                    or "Request failed"
                )
                enveloped = {
                    "status": False,
                    "success": False,
                    "status_code": response.status_code,
                    "message": msg,
                    "error": (
                        error_obj
                        if (isinstance(error_obj, dict) and error_obj)
                        else {
                            "code": code,
                            "message": msg,
                            "details": {},
                        }
                    ),
                    "data": None,
                }
            new_content = json.dumps(enveloped).encode("utf-8")

        headers = dict(response.headers)
        headers["content-length"] = str(len(new_content))
        return Response(
            content=new_content,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.APP_ENV == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    # Startup
    setup_logging(settings.LOG_LEVEL)

    # Auto-run pending database migrations on startup in development
    if settings.APP_ENV == "development":
        try:
            from alembic import command
            from alembic.config import Config

            def _upgrade() -> None:
                alembic_cfg = Config("alembic.ini")
                command.upgrade(alembic_cfg, "head")

            await asyncio.to_thread(_upgrade)
        except Exception as e:
            logging.getLogger("inzar.startup").warning("Auto-migration check notice: %s", e)

    # Optional Sentry tracking hook
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk  # type: ignore[import-not-found]

            sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=settings.APP_ENV)
        except Exception:
            pass

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

    # Middleware execution stack (Starlette executes in reverse order of addition)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(ResponseEnvelopeMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
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
