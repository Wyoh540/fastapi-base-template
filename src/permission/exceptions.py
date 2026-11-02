"""Permission-specific exceptions derived from the global :class:`AppError`."""

from src.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from src.permission.constants import ErrorCode


class RoleNotFound(NotFoundError):
    code = ErrorCode.ROLE_NOT_FOUND
    message = "That role does not exist."


class RoleAlreadyExists(ConflictError):
    code = ErrorCode.ROLE_ALREADY_EXISTS
    message = "A role with that name already exists."


class PermissionNotFound(NotFoundError):
    code = ErrorCode.PERMISSION_NOT_FOUND
    message = "That permission does not exist."


class UserRoleNotFound(NotFoundError):
    code = ErrorCode.USER_ROLE_NOT_FOUND
    message = "That user does not hold the requested role."


class AccessDenied(PermissionDeniedError):
    """Raised when the caller's roles do not cover the requested permission."""

    code = ErrorCode.ACCESS_DENIED
    message = "You do not have permission to perform this action."


class AdminRoleProtected(ConflictError):
    """The ``admin`` role may not be deleted — it is the way back in."""

    code = ErrorCode.ADMIN_ROLE_PROTECTED
    message = "The admin role cannot be deleted."
