"""Posts domain Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.posts.constants import PostStatus


class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    status: PostStatus = PostStatus.DRAFT


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    status: PostStatus | None = None


class PostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    author_id: uuid.UUID
    status: PostStatus
    view_count: int
    created_at: datetime
    updated_at: datetime


class PostSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: PostStatus
    author_id: uuid.UUID
    created_at: datetime
