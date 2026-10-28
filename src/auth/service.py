"""Auth domain business logic."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.config import auth_settings
from src.auth.exceptions import (
    EmailAlreadyRegistered,
    InactiveUser,
    InvalidCredentials,
    UsernameAlreadyTaken,
)
from src.auth.models import User
from src.auth.schemas import UserCreate
from src.auth.utils import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_identifier(session: AsyncSession, identifier: str) -> User | None:
    """Look a user up by email *or* username.

    The OAuth2 password grant calls the field ``username``; accepting both
    keeps the Swagger UI usable with whichever identifier the user remembers.
    """
    result = await session.execute(
        select(User).where(or_(User.email == identifier.lower(), User.username == identifier))
    )
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, payload: UserCreate) -> User:
    """Register a new user, rejecting duplicate email/username."""
    email = payload.email.lower()
    if await get_user_by_email(session, email) is not None:
        raise EmailAlreadyRegistered

    existing_username = await session.execute(
        select(User.id).where(User.username == payload.username)
    )
    if existing_username.scalar_one_or_none() is not None:
        raise UsernameAlreadyTaken

    user = User(
        email=email,
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate(session: AsyncSession, identifier: str, password: str) -> User:
    """Validate credentials and return the active user.

    ``identifier`` is the OAuth2 ``username`` field — an email address or a
    username both work.
    """
    user = await get_user_by_identifier(session, identifier)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentials
    if not user.is_active:
        raise InactiveUser
    return user


def issue_token_pair(user: User) -> tuple[str, str]:
    """Return an ``(access_token, refresh_token)`` pair for ``user``."""
    subject = str(user.id)
    claims = {"email": user.email, "username": user.username}
    return (
        create_access_token(subject, **claims),
        create_refresh_token(subject, **claims),
    )


def access_token_ttl_seconds() -> int:
    return int(auth_settings.access_token_expire.total_seconds())
