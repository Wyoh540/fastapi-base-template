"""Global exception types and their HTTP representation."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """OpenAPI schema for every error envelope produced by the API."""

    code: str
    message: str
    details: Any | None = None


# Starlette renamed the 422 constant in 1.10. Resolve it defensively so the
# project keeps working on both older and newer Starlette releases.
HTTP_422_UNPROCESSABLE: int = (
    getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", None) or status.HTTP_422_UNPROCESSABLE_ENTITY
)


class AppError(Exception):
    """Base class for every domain-agnostic application error.

    Domain packages subclass this and override the class attributes to describe
    their own failure semantics.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, details: Any = None) -> None:
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The request conflicts with the current state of the resource."


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    message = "Authentication failed."


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "You do not have permission to perform this action."


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the JSON error envelope to the app.

    Domain errors are rendered uniformly so clients never have to parse
    FastAPI's ``{"detail": ...}`` shape in one place and our envelope in
    another.
    """

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        """Render FastAPI's own 422s in the same envelope as domain errors."""
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE,
            content={
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
            },
        )
