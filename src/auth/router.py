"""Auth domain HTTP endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Form, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from src.auth.config import auth_settings
from src.auth.constants import TokenType
from src.auth.dependencies import CurrentUser, DbSession
from src.auth.exceptions import RefreshTokenRequired, TokenInvalid, UnsupportedGrantType
from src.auth.models import User
from src.auth.schemas import Message, TokenPair, UserCreate, UserRead
from src.auth.service import (
    access_token_ttl_seconds,
    authenticate,
    create_user,
    get_user_by_id,
    issue_token_pair,
)
from src.auth.utils import decode_token
from src.exceptions import HTTP_422_UNPROCESSABLE, ErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"


@router.post(
    "/signup",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Creates an account and returns an access/refresh token pair.",
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Email or username already taken",
        },
        HTTP_422_UNPROCESSABLE: {
            "model": ErrorResponse,
            "description": "Validation error",
        },
    },
)
async def signup(payload: UserCreate, response: Response, session: DbSession) -> dict:
    user = await create_user(session, payload)
    return _token_response(user, response)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Exchange credentials for tokens",
    description=(
        "OAuth2 password grant. Submit `username` (email or username) and `password` "
        "as form data — this is the endpoint Swagger UI's Authorize button calls."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid credentials",
        },
        HTTP_422_UNPROCESSABLE: {
            "model": ErrorResponse,
            "description": "Missing form fields",
        },
    },
)
async def login(
    response: Response,
    session: DbSession,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> dict:
    user = await authenticate(session, form_data.username, form_data.password)
    return _token_response(user, response)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate a refresh token",
    description=(
        "OAuth2 refresh_token grant. The token is read from the `refresh_token` "
        "cookie when present, otherwise from the form body. A new access/refresh "
        "pair is issued on success."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Unsupported grant type",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid refresh token",
        },
    },
)
async def refresh(
    response: Response,
    session: DbSession,
    form_refresh_token: Annotated[str | None, Form(alias="refresh_token")] = None,
    grant_type: Annotated[str | None, Form(description="Must be 'refresh_token'")] = None,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> dict:
    if grant_type is not None and grant_type != "refresh_token":
        raise UnsupportedGrantType

    token = refresh_token or form_refresh_token
    if not token:
        raise RefreshTokenRequired

    claims = decode_token(token, expect_type=TokenType.REFRESH)
    user = await get_user_by_id(session, _parse_subject(claims.get("sub")))
    if user is None:
        raise TokenInvalid
    return _token_response(user, response)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the authenticated user",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Not authenticated",
        },
    },
)
async def read_me(current_user: CurrentUser) -> object:
    return current_user


@router.post("/logout", response_model=Message, summary="Clear the refresh cookie")
async def logout(response: Response) -> dict:
    response.delete_cookie(REFRESH_COOKIE_NAME)
    return {"message": "Logged out."}


def _token_response(user: User, response: Response) -> dict:
    access_token, refresh_token = issue_token_pair(user)
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=auth_settings.SECURE_COOKIES,
        samesite="lax",
        max_age=int(auth_settings.REFRESH_TOKEN_EXP.total_seconds()),
        path="/auth",
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": access_token_ttl_seconds(),
    }


def _parse_subject(subject: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(subject))
    except (TypeError, ValueError) as exc:
        raise TokenInvalid from exc
