"""Permission domain HTTP endpoints.

Every endpoint is guarded by a permission, expressed as an HTTP method plus a
path pattern. The seeded ``admin`` role holds ``/api/v1/permission/*`` for all
four methods, so the endpoints are reachable — and only reachable — by admins.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from src.auth.dependencies import DbSession
from src.auth.models import User
from src.exceptions import ErrorResponse
from src.permission import service
from src.permission.dependencies import require_permission
from src.permission.schemas import (
    PermissionGrant,
    PermissionRead,
    RoleCreate,
    RoleRead,
    UserRolesRead,
)

router = APIRouter(prefix="/permission", tags=["permission"])

RoleName = Path(description="Role name", min_length=2, max_length=64)
UserId = Path(description="User identifier")
PermissionId = Path(description="Permission identifier")

# One permission alias per endpoint. Each states the HTTP method and the path
# pattern the caller must hold a permission for — the same values the seeded
# policies are written with.
CanListRoles = Annotated[User, Depends(require_permission("GET", "/api/v1/permission/roles"))]
CanCreateRole = Annotated[User, Depends(require_permission("POST", "/api/v1/permission/roles"))]
CanReadRole = Annotated[User, Depends(require_permission("GET", "/api/v1/permission/roles/*"))]
CanDeleteRole = Annotated[User, Depends(require_permission("DELETE", "/api/v1/permission/roles/*"))]
CanListRolePermissions = Annotated[
    User, Depends(require_permission("GET", "/api/v1/permission/roles/*/permissions"))
]
CanGrantPermission = Annotated[
    User, Depends(require_permission("PUT", "/api/v1/permission/roles/*/permissions"))
]
CanRevokePermission = Annotated[
    User, Depends(require_permission("DELETE", "/api/v1/permission/roles/*/permissions/*"))
]
CanListUserRoles = Annotated[
    User, Depends(require_permission("GET", "/api/v1/permission/users/*/roles"))
]
CanAssignRole = Annotated[
    User, Depends(require_permission("PUT", "/api/v1/permission/users/*/roles/*"))
]
CanRevokeRole = Annotated[
    User, Depends(require_permission("DELETE", "/api/v1/permission/users/*/roles/*"))
]


def _permission_payload(rule) -> dict:
    """Render a policy row as a permission object."""
    return {"id": rule.id, "obj": rule.v1, "act": rule.v2}


@router.get(
    "/roles",
    response_model=list[RoleRead],
    summary="List roles",
    description="Lists every role together with the permissions granted to it.",
    responses={status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Forbidden"}},
)
async def list_roles(
    _: CanListRoles,
    session: DbSession,
) -> list[dict]:
    roles = await service.list_roles(session)
    permissions = await service.list_all_permissions(session)

    grouped: dict[str, list[dict]] = {}
    for rule in permissions:
        if rule.v0 is not None:
            grouped.setdefault(rule.v0, []).append(_permission_payload(rule))

    return [
        {
            "name": role.name,
            "description": role.description,
            "created_at": role.created_at,
            "permissions": grouped.get(role.name, []),
        }
        for role in roles
    ]


@router.post(
    "/roles",
    response_model=RoleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a role",
    description="Creates a role. The name becomes the subject of its Casbin policies.",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Forbidden"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Role already exists"},
    },
)
async def create_role(
    payload: RoleCreate,
    _: CanCreateRole,
    session: DbSession,
) -> dict:
    role = await service.create_role(session, payload.name, payload.description)
    return {
        "name": role.name,
        "description": role.description,
        "created_at": role.created_at,
        "permissions": [],
    }


@router.get(
    "/roles/{role_name}",
    response_model=RoleRead,
    summary="Read a role",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Forbidden"},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Role not found"},
    },
)
async def read_role(
    _: CanReadRole,
    session: DbSession,
    role_name: str = RoleName,
) -> dict:
    role = await service.require_role(session, role_name)
    permissions = await service.list_permissions(session, role_name)
    return {
        "name": role.name,
        "description": role.description,
        "created_at": role.created_at,
        "permissions": [_permission_payload(rule) for rule in permissions],
    }


@router.delete(
    "/roles/{role_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a role",
    description="Deletes a role together with its permissions and assignments.",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Forbidden"},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Role not found"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Role is protected"},
    },
)
async def delete_role(
    _: CanDeleteRole,
    session: DbSession,
    role_name: str = RoleName,
) -> None:
    role = await service.require_role(session, role_name)
    await service.delete_role(session, role)


@router.get(
    "/roles/{role_name}/permissions",
    response_model=list[PermissionRead],
    summary="List the permissions of a role",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Forbidden"},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Role not found"},
    },
)
async def list_role_permissions(
    _: CanListRolePermissions,
    session: DbSession,
    role_name: str = RoleName,
) -> list[dict]:
    await service.require_role(session, role_name)
    permissions = await service.list_permissions(session, role_name)
    return [_permission_payload(rule) for rule in permissions]


@router.put(
    "/roles/{role_name}/permissions",
    response_model=PermissionRead,
    summary="Grant a permission to a role",
    description="Grants a permission. Granting the same permission twice is a no-op.",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Forbidden"},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Role not found"},
    },
)
async def grant_role_permission(
    payload: PermissionGrant,
    _: CanGrantPermission,
    session: DbSession,
    role_name: str = RoleName,
) -> dict:
    rule, _created = await service.grant_permission(session, role_name, payload.obj, payload.act)
    return _permission_payload(rule)


@router.delete(
    "/roles/{role_name}/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a permission from a role",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Forbidden"},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Permission not found"},
    },
)
async def revoke_role_permission(
    _: CanRevokePermission,
    session: DbSession,
    role_name: str = RoleName,
    permission_id: int = PermissionId,
) -> None:
    await service.revoke_permission(session, role_name, permission_id)


@router.get(
    "/users/{user_id}/roles",
    response_model=UserRolesRead,
    summary="List the roles of a user",
    responses={status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Forbidden"}},
)
async def list_user_roles(
    _: CanListUserRoles,
    session: DbSession,
    user_id: uuid.UUID = UserId,
) -> dict:
    roles = await service.list_user_roles(session, user_id)
    return {"user_id": user_id, "roles": roles}


@router.put(
    "/users/{user_id}/roles/{role_name}",
    response_model=UserRolesRead,
    summary="Assign a role to a user",
    description="Assigns a role. Assigning the same role twice is a no-op.",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Forbidden"},
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Role or user not found",
        },
    },
)
async def assign_user_role(
    _: CanAssignRole,
    session: DbSession,
    user_id: uuid.UUID = UserId,
    role_name: str = RoleName,
) -> dict:
    await service.assign_role(session, user_id, role_name)
    roles = await service.list_user_roles(session, user_id)
    return {"user_id": user_id, "roles": roles}


@router.delete(
    "/users/{user_id}/roles/{role_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a role from a user",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Forbidden"},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Role not held"},
    },
)
async def revoke_user_role(
    _: CanRevokeRole,
    session: DbSession,
    user_id: uuid.UUID = UserId,
    role_name: str = RoleName,
) -> None:
    await service.revoke_role(session, user_id, role_name)
