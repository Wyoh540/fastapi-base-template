"""Reusable FastAPI dependencies for the posts domain."""

import uuid
from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import valid_user
from src.auth.models import User
from src.database import get_db
from src.posts.exceptions import NotPostOwner, PostNotFound
from src.posts.models import Post
from src.posts.service import get_post

DbSession = Annotated[AsyncSession, Depends(get_db)]

ValidPostId = Annotated[uuid.UUID, Path(description="Post identifier")]


async def valid_post_id(post_id: ValidPostId, session: DbSession) -> Post:
    """Load a post by id, raising ``PostNotFound`` when missing."""
    post = await get_post(session, post_id)
    if post is None:
        raise PostNotFound
    return post


async def valid_owned_post(
    post: Annotated[Post, Depends(valid_post_id)],
    current_user: Annotated[User, Depends(valid_user)],
) -> Post:
    """Chain the ownership check on top of :func:`valid_post_id`.

    Because FastAPI caches dependencies per request, ``valid_post_id`` runs
    exactly once even though both dependencies are declared here.
    """
    if post.author_id != current_user.id:
        raise NotPostOwner
    return post


OwnedPost = Annotated[Post, Depends(valid_owned_post)]
