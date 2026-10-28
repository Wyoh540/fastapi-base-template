"""Password hashing and JWT helpers."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from src.auth.config import auth_settings
from src.auth.constants import TokenType
from src.auth.exceptions import TokenExpired, TokenInvalid

# bcrypt only consumes the first 72 bytes of a secret. Pre-hashing with SHA-256
# makes the input a fixed 32 bytes, so long passphrases are never silently
# truncated (which would let two different passwords match).
_PRE_HASH_LENGTH = 32


def _prepare(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    """Return a bcrypt hash of ``password`` as an ASCII string."""
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time comparison of ``password`` against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        # Malformed hash in storage -> treat as a failed login, never a 500.
        return False


def _build_token(
    subject: str,
    token_type: TokenType,
    secret: str,
    expires_in: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_in,
        **(extra_claims or {}),
    }
    return jwt.encode(payload, secret, algorithm=auth_settings.JWT_ALG)


def create_access_token(subject: str, **extra_claims: Any) -> str:
    return _build_token(
        subject=subject,
        token_type=TokenType.ACCESS,
        secret=auth_settings.JWT_SECRET,
        expires_in=auth_settings.access_token_expire,
        extra_claims=extra_claims,
    )


def create_refresh_token(subject: str, **extra_claims: Any) -> str:
    return _build_token(
        subject=subject,
        token_type=TokenType.REFRESH,
        secret=auth_settings.REFRESH_TOKEN_KEY,
        expires_in=auth_settings.REFRESH_TOKEN_EXP,
        extra_claims=extra_claims,
    )


def decode_token(token: str, *, expect_type: TokenType) -> dict[str, Any]:
    """Decode and validate a token, raising domain errors on failure."""
    secret = (
        auth_settings.JWT_SECRET
        if expect_type is TokenType.ACCESS
        else auth_settings.REFRESH_TOKEN_KEY
    )
    try:
        payload = jwt.decode(token, secret, algorithms=[auth_settings.JWT_ALG])
    except ExpiredSignatureError as exc:
        raise TokenExpired from exc
    except InvalidTokenError as exc:
        raise TokenInvalid from exc

    if payload.get("type") != expect_type.value:
        raise TokenInvalid
    return payload
