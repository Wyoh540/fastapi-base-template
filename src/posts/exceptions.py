"""Posts-specific exceptions derived from the global :class:`AppError`."""

from src.exceptions import AppError, ConflictError, NotFoundError, PermissionDeniedError
from src.posts.constants import ErrorCode


class PostError(AppError):
    """Base class for posts domain failures."""


class PostNotFound(NotFoundError):
    code = ErrorCode.POST_NOT_FOUND
    message = "That post does not exist."


class NotPostOwner(PermissionDeniedError):
    code = ErrorCode.NOT_POST_OWNER
    message = "Only the author can modify this post."


class PostArchived(ConflictError):
    code = ErrorCode.POST_ARCHIVED
    message = "Archived posts cannot be modified."
