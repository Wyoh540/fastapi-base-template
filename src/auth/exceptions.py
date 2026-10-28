"""Auth-specific exceptions derived from the global :class:`AppError`."""

from fastapi import status

from src.auth.constants import ErrorCode
from src.exceptions import AppError, AuthenticationError, ConflictError


class AuthError(AuthenticationError):
    """Base class for authentication failures."""

    code = ErrorCode.TOKEN_INVALID


class InvalidCredentials(AuthError):
    code = ErrorCode.INVALID_CREDENTIALS
    message = "Invalid email or password."


class InactiveUser(AuthError):
    code = ErrorCode.USER_INACTIVE
    message = "This account is deactivated."


class TokenExpired(AuthError):
    code = ErrorCode.TOKEN_EXPIRED
    message = "The token has expired."


class TokenInvalid(AuthError):
    code = ErrorCode.TOKEN_INVALID
    message = "The token is invalid."


class RefreshTokenRequired(AuthError):
    code = ErrorCode.REFRESH_TOKEN_REQUIRED
    message = "A refresh token is required for this operation."


class UnsupportedGrantType(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = ErrorCode.UNSUPPORTED_GRANT_TYPE
    message = "The grant_type must be 'refresh_token'."


class EmailAlreadyRegistered(ConflictError):
    code = ErrorCode.EMAIL_TAKEN
    message = "That email address is already registered."


class UsernameAlreadyTaken(ConflictError):
    code = ErrorCode.USERNAME_TAKEN
    message = "That username is already taken."
