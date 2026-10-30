import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("inzar.errors")


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"
    message: str = "A bad request occurred"

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Resource conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Authentication required"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "Access denied"


class RateLimitExceededError(AppError):
    status_code = 429
    code = "rate_limit_exceeded"
    message = "Too many requests. Please try again later."


class GoneError(AppError):
    status_code = 410
    code = "gone"
    message = "Resource is no longer available"


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"
    message = "Invalid request"


def format_error_response(
    code: str,
    message: str,
    details: Any = None,
    status_code: int = 400,
) -> dict[str, Any]:
    return {
        "status": False,
        "success": False,
        "status_code": status_code,
        "message": message,
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
        },
        "data": None,
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=format_error_response(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                status_code=exc.status_code,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(item) for item in err.get("loc", []))
            errors.append(
                {"field": loc, "message": err.get("msg", ""), "type": err.get("type", "")}
            )
        return JSONResponse(
            status_code=422,
            content=format_error_response(
                code="validation_error",
                message="Invalid request input parameters",
                details={"errors": errors},
                status_code=422,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        msg = str(exc.detail) if isinstance(exc.detail, str) else "HTTP error"
        details: dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
        code = "http_error"
        if exc.status_code == 404:
            code = "not_found"
        elif exc.status_code == 401:
            code = "unauthorized"
        elif exc.status_code == 403:
            code = "forbidden"
        return JSONResponse(
            status_code=exc.status_code,
            content=format_error_response(
                code=code,
                message=msg,
                details=details,
                status_code=exc.status_code,
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database error intercepted: %s", exc, exc_info=True)
        err_msg = str(exc)
        if "does not exist" in err_msg or "UndefinedTableError" in err_msg:
            return JSONResponse(
                status_code=500,
                content=format_error_response(
                    code="database_migration_required",
                    message="Database table or relation does not exist. Please run database migrations (`uv run alembic upgrade head`).",
                    details={"internal_error": "Missing database tables"},
                    status_code=500,
                ),
            )
        return JSONResponse(
            status_code=500,
            content=format_error_response(
                code="database_error",
                message="A database operation failed",
                details={},
                status_code=500,
            ),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content=format_error_response(
                code="internal_server_error",
                message="An unexpected server error occurred",
                details={},
                status_code=500,
            ),
        )
