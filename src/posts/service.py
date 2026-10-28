"""Posts domain business logic.

Aggregation and shaping happen in SQL where possible; rows are hydrated into
Pydantic models only for response validation.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pagination import PaginationParams
from src.posts.constants import PostStatus
from src.posts.exceptions import PostArchived
from src.posts.models import Post
from src.posts.schemas import PostCreate, PostUpdate
from src.posts.utils import is_editable


async def create_post(session: AsyncSession, author_id: uuid.UUID, payload: PostCreate) -> Post:
    post = Post(
        title=payload.title,
        content=payload.content,
        status=payload.status.value,
        author_id=author_id,
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


async def get_post(session: AsyncSession, post_id: uuid.UUID) -> Post | None:
    result = await session.execute(select(Post).where(Post.id == post_id))
    return result.scalar_one_or_none()


async def list_posts(
    session: AsyncSession,
    *,
    params: PaginationParams,
    author_id: uuid.UUID | None = None,
    status: PostStatus | None = None,
) -> tuple[list[Post], int]:
    """Return one page of posts plus the total row count (single query each)."""
    filters = []
    if author_id is not None:
        filters.append(Post.author_id == author_id)
    if status is not None:
        filters.append(Post.status == status.value)

    count_query = select(func.count()).select_from(Post).where(*filters)
    total = (await session.execute(count_query)).scalar_one()

    page_query = (
        select(Post)
        .where(*filters)
        .order_by(Post.created_at.desc())
        .offset(params.offset)
        .limit(params.limit)
    )
    rows = (await session.execute(page_query)).scalars().all()
    return list(rows), int(total)


async def update_post(session: AsyncSession, post: Post, payload: PostUpdate) -> Post:
    if not is_editable(post.status):
        raise PostArchived

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(post, field, value.value if isinstance(value, PostStatus) else value)
    await session.commit()
    await session.refresh(post)
    return post


async def delete_post(session: AsyncSession, post: Post) -> None:
    await session.delete(post)
    await session.commit()


async def increment_view_count(session: AsyncSession, post_id: uuid.UUID) -> None:
    """Atomic counter bump — no read-modify-write round trip."""
    await session.execute(
        Post.__table__.update().where(Post.id == post_id).values(view_count=Post.view_count + 1)
    )
    await session.commit()
