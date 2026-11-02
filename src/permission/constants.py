"""Domain constants and error codes for the permission bounded context."""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable, machine-readable error codes exposed to API clients."""

    ROLE_NOT_FOUND = "role_not_found"
    ROLE_ALREADY_EXISTS = "role_already_exists"
    USER_ROLE_NOT_FOUND = "user_role_not_found"
    PERMISSION_NOT_FOUND = "permission_not_found"
    ACCESS_DENIED = "access_denied"
    ADMIN_ROLE_PROTECTED = "admin_role_protected"
    INVALID_PERMISSION = "invalid_permission"


class PolicyType(StrEnum):
    """The ``ptype`` values Casbin understands.

    Only ``p`` (policy) rows are persisted. The ``g`` (role assignment) rows
    live in the ``user_role`` table instead — see ``src/permission/enforcer.py``.
    """

    POLICY = "p"
    GROUPING = "g"
