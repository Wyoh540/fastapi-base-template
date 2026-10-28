"""Reusable FastAPI dependencies for the auth domain."""

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.constants import TokenType
from src.auth.exceptions import TokenInvalid
from src.auth.models import User
from src.auth.service import get_user_by_id
from src.auth.utils import decode_token
from src.config import API_PREFIX
from src.database import get_db

# `tokenUrl` is what Swagger UI's *Authorize* button posts the credentials to,
# so it must point at the token endpoint of this application.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{API_PREFIX}/auth/login",
    auto_error=False,
    description="OAuth2 password flow — use the Authorize button in /docs.",
)

DbSession = Annotated[AsyncSession, Depends(get_db)]
AccessToken = Annotated[str | None, Depends(oauth2_scheme)]


async def parse_jwt_data(token: AccessToken) -> dict:
    """Validate the bearer token and return its claims."""
    if not token:
        raise TokenInvalid
    return decode_token(token, expect_type=TokenType.ACCESS)


async def valid_user(
    token_data: Annotated[dict, Depends(parse_jwt_data)],
    session: DbSession,
) -> User:
    """Load the user referenced by the access token."""
    subject = token_data.get("sub")
    try:
        user_id = uuid.UUID(subject)
    except (TypeError, ValueError) as exc:
        raise TokenInvalid from exc

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise TokenInvalid
    return user


CurrentUser = Annotated[User, Depends(valid_user)]
