import uuid
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found", details: dict[str, Any] | None = None):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class UnauthorizedError(AppException):
    def __init__(
        self, message: str = "Authentication required", details: dict[str, Any] | None = None
    ):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class ForbiddenError(AppException):
    def __init__(
        self,
        message: str = "Access denied: insufficient permissions",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class ValidationError(AppException):
    def __init__(
        self, message: str = "Invalid input payload", details: dict[str, Any] | None = None
    ):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


def make_error_envelope(
    code: str, message: str, trace_id: str | None = None, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "trace_id": trace_id or str(uuid.uuid4()),
            "details": details or {},
        }
    }


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content=make_error_envelope(
            code=exc.code, message=exc.message, trace_id=trace_id, details=exc.details
        ),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=make_error_envelope(
            code="REQUEST_VALIDATION_FAILED",
            message="Request data validation failed",
            trace_id=trace_id,
            details={"errors": exc.errors()},
        ),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content=make_error_envelope(
            code=f"HTTP_{exc.status_code}", message=str(exc.detail), trace_id=trace_id
        ),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    # Do not expose internal stack traces
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=make_error_envelope(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected internal server error occurred",
            trace_id=trace_id,
        ),
    )
