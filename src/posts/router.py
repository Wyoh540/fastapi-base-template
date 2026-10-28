"""Posts domain HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from src.auth.dependencies import CurrentUser
from src.exceptions import HTTP_422_UNPROCESSABLE, ErrorResponse
from src.pagination import PaginatedResponse, Pagination
from src.posts.constants import PostStatus
from src.posts.dependencies import DbSession, OwnedPost, valid_post_id
from src.posts.models import Post
from src.posts.schemas import PostCreate, PostRead, PostSummary, PostUpdate
from src.posts.service import (
    create_post,
    delete_post,
    increment_view_count,
    list_posts,
    update_post,
)

router = APIRouter(prefix="/posts", tags=["posts"])

PostDep = Annotated[Post, Depends(valid_post_id)]


@router.post(
    "",
    response_model=PostRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a post",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Not authenticated"},
        HTTP_422_UNPROCESSABLE: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def create(payload: PostCreate, current_user: CurrentUser, session: DbSession) -> object:
    return await create_post(session, current_user.id, payload)


@router.get(
    "",
    response_model=PaginatedResponse[PostSummary],
    summary="List posts",
    description="Returns one page of posts plus the total number of matching rows.",
)
async def index(
    session: DbSession,
    params: Pagination,
    post_status: Annotated[PostStatus | None, Query(alias="status")] = None,
) -> dict:
    rows, total = await list_posts(session, params=params, status=post_status)
    return {"items": rows, "total": total, "page": params.page, "page_size": params.page_size}


@router.get(
    "/mine",
    response_model=PaginatedResponse[PostSummary],
    summary="List the authenticated user's posts",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Not authenticated"},
    },
)
async def my_posts(current_user: CurrentUser, session: DbSession, params: Pagination) -> dict:
    rows, total = await list_posts(session, params=params, author_id=current_user.id)
    return {"items": rows, "total": total, "page": params.page, "page_size": params.page_size}


@router.get(
    "/{post_id}",
    response_model=PostRead,
    summary="Fetch a single post",
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Post not found"},
    },
)
async def show(post: PostDep) -> object:
    return post


@router.patch(
    "/{post_id}",
    response_model=PostRead,
    summary="Update a post",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Not the author"},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Post not found"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Post is archived"},
    },
)
async def update(payload: PostUpdate, post: OwnedPost, session: DbSession) -> object:
    return await update_post(session, post, payload)


@router.delete(
    "/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a post",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Not the author"},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Post not found"},
    },
)
async def remove(post: OwnedPost, session: DbSession) -> Response:
    await delete_post(session, post)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{post_id}/views",
    summary="Increment the view counter",
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Post not found"},
    },
)
async def track_view(post: PostDep, session: DbSession) -> dict:
    await increment_view_count(session, post.id)
    return {"message": "View recorded."}
