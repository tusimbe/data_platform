# src/api/errors.py
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.core.exceptions import (
    AppError,
    NotFoundError,
    ConflictError,
    ValidationError,
    ServiceUnavailableError,
    NotImplementedError_,
)

logger = logging.getLogger(__name__)

STATUS_CODE_MAP = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
}

DOMAIN_EXCEPTION_MAP: dict[type[AppError], tuple[int, str]] = {
    NotFoundError: (404, "NOT_FOUND"),
    ConflictError: (409, "CONFLICT"),
    ValidationError: (400, "BAD_REQUEST"),
    ServiceUnavailableError: (502, "BAD_GATEWAY"),
    NotImplementedError_: (501, "NOT_IMPLEMENTED"),
}


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(AppError)
    async def domain_exception_handler(request: Request, exc: AppError):
        status_code, code = DOMAIN_EXCEPTION_MAP.get(type(exc), (500, "INTERNAL_ERROR"))
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        code = STATUS_CODE_MAP.get(exc.status_code, "ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": str(exc.detail),
                    "details": None,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                    "details": None,
                }
            },
        )
