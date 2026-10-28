"""Domain constants and error codes for the auth bounded context."""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable, machine-readable error codes exposed to API clients."""

    INVALID_CREDENTIALS = "invalid_credentials"
    USER_INACTIVE = "user_inactive"
    EMAIL_TAKEN = "email_taken"
    USERNAME_TAKEN = "username_taken"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"
    REFRESH_TOKEN_REQUIRED = "refresh_token_required"
    UNSUPPORTED_GRANT_TYPE = "unsupported_grant_type"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
