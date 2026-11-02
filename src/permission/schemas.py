"""Permission domain Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=255)


class PermissionRead(BaseModel):
    """A single granted permission.

    The Casbin policy table stores its columns as ``v0..v5``; ``v1`` is the
    object (the path pattern) and ``v2`` the action (the HTTP method). The
    mapping happens where the row is rendered — see
    ``src.permission.router._permission_payload``.
    """

    id: int
    obj: str
    act: str


class PermissionGrant(BaseModel):
    obj: str = Field(
        min_length=1,
        max_length=255,
        description="Object pattern the permission applies to, e.g. /api/v1/posts/*",
    )
    act: str = Field(
        min_length=1,
        max_length=16,
        pattern=r"^[A-Z]+$",
        description="HTTP method the permission applies to, e.g. GET",
    )


class RoleRead(BaseModel):
    name: str
    description: str | None = None
    created_at: datetime
    permissions: list[PermissionRead] = Field(default_factory=list)


class UserRolesRead(BaseModel):
    user_id: uuid.UUID
    roles: list[str] = Field(default_factory=list)


class Message(BaseModel):
    message: str
