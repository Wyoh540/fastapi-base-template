"""Permission domain business logic.

Policy rows are written through the ORM rather than through the Casbin
adapter on purpose: the adapter's ``save_policy()`` deletes the whole table
before rewriting it, and the adapter has no notion of "remove this one row by
primary key". The enforcement path reads the very same table through the
adapter, so both sides stay in sync.
"""

import logging
import re
import secrets
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import service as auth_service
from src.auth.models import User
from src.auth.schemas import UserCreate
from src.exceptions import NotFoundError
from src.permission.config import permission_settings
from src.permission.constants import PolicyType
from src.permission.exceptions import (
    AdminRoleProtected,
    PermissionNotFound,
    RoleAlreadyExists,
    RoleNotFound,
    UserRoleNotFound,
)
from src.permission.models import CasbinRule, Role, UserRole

logger = logging.getLogger(__name__)

PERMISSION_NAMESPACE = "/api/v1/permission/*"
POSTS_NAMESPACE = "/api/v1/posts/*"

SEED_ROLES: dict[str, str] = {
    "admin": "Full access to every endpoint.",
    "editor": "Read and write access to posts.",
    "reader": "Read-only access to posts.",
}


def _seed_roles() -> dict[str, str]:
    """The default roles, including the configured admin role name."""
    roles = dict(SEED_ROLES)
    roles.setdefault(permission_settings.ADMIN_ROLE, "Full access to every endpoint.")
    return roles


def _seed_policies() -> list[tuple[str, str, str]]:
    """The default ``(role, obj, act)`` policies.

    The ``admin`` role owns the permission endpoints themselves — that is what
    makes the authorization loop observable. The post permissions are seeded
    ahead of time; the posts endpoints do not enforce them yet.
    """
    admin = permission_settings.ADMIN_ROLE
    policies: list[tuple[str, str, str]] = []
    for act in ("GET", "POST", "PUT", "DELETE"):
        policies.append((admin, PERMISSION_NAMESPACE, act))
        policies.append((admin, POSTS_NAMESPACE, act))
    policies.extend(
        [
            ("editor", POSTS_NAMESPACE, "GET"),
            ("editor", POSTS_NAMESPACE, "POST"),
            ("editor", POSTS_NAMESPACE, "PUT"),
            ("reader", POSTS_NAMESPACE, "GET"),
        ]
    )
    return policies


# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #


async def list_roles(session: AsyncSession) -> list[Role]:
    result = await session.execute(select(Role).order_by(Role.name))
    return list(result.scalars().all())


async def get_role(session: AsyncSession, name: str) -> Role | None:
    return await session.get(Role, name)


async def require_role(session: AsyncSession, name: str) -> Role:
    role = await get_role(session, name)
    if role is None:
        raise RoleNotFound
    return role


async def create_role(session: AsyncSession, name: str, description: str | None) -> Role:
    if await get_role(session, name) is not None:
        raise RoleAlreadyExists

    role = Role(name=name, description=description)
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return role


async def delete_role(session: AsyncSession, role: Role) -> None:
    """Delete a role together with its permissions and its assignments."""
    if role.name == permission_settings.ADMIN_ROLE:
        raise AdminRoleProtected

    # SQLite only honours ON DELETE CASCADE when the foreign_keys pragma is
    # enabled, so the dependent rows are removed explicitly to keep SQLite and
    # PostgreSQL behaving the same.
    await session.execute(
        delete(CasbinRule).where(
            CasbinRule.ptype == PolicyType.POLICY.value, CasbinRule.v0 == role.name
        )
    )
    await session.execute(delete(UserRole).where(UserRole.role_name == role.name))
    await session.delete(role)
    await session.commit()


# --------------------------------------------------------------------------- #
# Permissions
# --------------------------------------------------------------------------- #


async def list_permissions(session: AsyncSession, role_name: str) -> list[CasbinRule]:
    result = await session.execute(
        select(CasbinRule)
        .where(CasbinRule.ptype == PolicyType.POLICY.value, CasbinRule.v0 == role_name)
        .order_by(CasbinRule.id)
    )
    return list(result.scalars().all())


async def list_all_permissions(session: AsyncSession) -> list[CasbinRule]:
    result = await session.execute(
        select(CasbinRule)
        .where(CasbinRule.ptype == PolicyType.POLICY.value)
        .order_by(CasbinRule.id)
    )
    return list(result.scalars().all())


async def grant_permission(
    session: AsyncSession, role_name: str, obj: str, act: str
) -> tuple[CasbinRule, bool]:
    """Grant a permission to a role.

    Returns the policy row and whether it was created — granting the same
    permission twice is a no-op rather than an error.
    """
    await require_role(session, role_name)

    existing = await session.execute(
        select(CasbinRule).where(
            CasbinRule.ptype == PolicyType.POLICY.value,
            CasbinRule.v0 == role_name,
            CasbinRule.v1 == obj,
            CasbinRule.v2 == act,
        )
    )
    rule = existing.scalar_one_or_none()
    if rule is not None:
        return rule, False

    rule = CasbinRule(ptype=PolicyType.POLICY.value, v0=role_name, v1=obj, v2=act)
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule, True


async def revoke_permission(session: AsyncSession, role_name: str, permission_id: int) -> None:
    rule = await session.get(CasbinRule, permission_id)
    if rule is None or rule.ptype != PolicyType.POLICY.value or rule.v0 != role_name:
        raise PermissionNotFound

    await session.delete(rule)
    await session.commit()


# --------------------------------------------------------------------------- #
# Role assignments
# --------------------------------------------------------------------------- #


async def list_user_roles(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    result = await session.execute(
        select(UserRole.role_name).where(UserRole.user_id == user_id).order_by(UserRole.role_name)
    )
    return list(result.scalars().all())


async def assign_role(session: AsyncSession, user_id: uuid.UUID, role_name: str) -> bool:
    """Assign a role to a user. Returns whether the assignment was created."""
    await require_role(session, role_name)

    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("That user does not exist.")

    existing = await session.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_name == role_name)
    )
    if existing.scalar_one_or_none() is not None:
        return False

    session.add(UserRole(user_id=user_id, role_name=role_name))
    await session.commit()
    return True


async def revoke_role(session: AsyncSession, user_id: uuid.UUID, role_name: str) -> None:
    existing = await session.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_name == role_name)
    )
    assignment = existing.scalar_one_or_none()
    if assignment is None:
        raise UserRoleNotFound

    await session.delete(assignment)
    await session.commit()


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #


def _seed_username(email: str) -> str:
    """Derive a username that satisfies the auth domain's username rules."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", email.split("@")[0])
    if len(cleaned) < 3:
        cleaned = "seed-admin"
    return cleaned[:64]


async def _ensure_policy(session: AsyncSession, role_name: str, obj: str, act: str) -> None:
    existing = await session.execute(
        select(CasbinRule).where(
            CasbinRule.ptype == PolicyType.POLICY.value,
            CasbinRule.v0 == role_name,
            CasbinRule.v1 == obj,
            CasbinRule.v2 == act,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    session.add(CasbinRule(ptype=PolicyType.POLICY.value, v0=role_name, v1=obj, v2=act))
    await session.commit()


async def _ensure_admin_account(session: AsyncSession) -> None:
    email = permission_settings.SEED_ADMIN_EMAIL
    user = await auth_service.get_user_by_email(session, email)
    if user is None:
        password = permission_settings.SEED_ADMIN_PASSWORD or secrets.token_urlsafe(12)
        user = await auth_service.create_user(
            session,
            UserCreate(email=email, username=_seed_username(email), password=password),
        )
        if not permission_settings.SEED_ADMIN_PASSWORD:
            logger.warning(
                "Seeded admin account %s with generated password: %s — change it.",
                email,
                password,
            )

    await assign_role(session, user.id, permission_settings.ADMIN_ROLE)


async def seed(session: AsyncSession) -> None:
    """Create the default roles, policies and admin account.

    Safe to run on every startup: every step checks whether the row already
    exists before writing it.
    """
    for name, description in _seed_roles().items():
        if await get_role(session, name) is None:
            session.add(Role(name=name, description=description))
    await session.commit()

    for role_name, obj, act in _seed_policies():
        await _ensure_policy(session, role_name, obj, act)

    await _ensure_admin_account(session)
