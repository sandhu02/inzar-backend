from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


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


def format_error_response(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=format_error_response(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Standardize Pydantic validation errors
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
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Any, exc: StarletteHTTPException) -> JSONResponse:
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
            content=format_error_response(code=code, message=msg, details=details),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        import logging

        logging.getLogger("inzar.errors").exception("Unhandled server exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content=format_error_response(
                code="internal_server_error",
                message="An unexpected server error occurred",
                details={},
            ),
        )
