"""Domain constants and error codes for the posts bounded context."""

from enum import StrEnum


class ErrorCode(StrEnum):
    POST_NOT_FOUND = "post_not_found"
    NOT_POST_OWNER = "not_post_owner"
    POST_ARCHIVED = "post_archived"
    INVALID_PAGE = "invalid_page"


class PostStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
