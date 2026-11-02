"""Reusable FastAPI dependencies for the permission domain."""

from collections.abc import Awaitable, Callable

from src.auth.dependencies import CurrentUser, DbSession
from src.auth.models import User
from src.permission.enforcer import build_user_enforcer
from src.permission.exceptions import AccessDenied


def require_permission(act: str, obj: str) -> Callable[..., Awaitable[User]]:
    """Build a dependency that enforces one permission on the current user.

    ``obj`` is a path pattern such as ``/api/v1/permission/roles/*`` and
    ``act`` an HTTP method such as ``GET``. The check runs against the
    permissions the user's roles grant — see
    :func:`src.permission.enforcer.build_user_enforcer`.

    Usage — declare one alias per endpoint in the router module::

        CanListRoles = Annotated[
            User, Depends(require_permission("GET", "/api/v1/permission/roles"))
        ]
    """

    async def dependency(current_user: CurrentUser, session: DbSession) -> User:
        enforcer = await build_user_enforcer(session, current_user.id)
        if not enforcer.enforce(str(current_user.id), obj, act):
            raise AccessDenied
        return current_user

    dependency.__name__ = f"require_permission_{act.lower()}_{obj.strip('/').replace('/', '_')}"
    return dependency
