"""Integration tests for the permission domain.

Every test runs against the real in-memory SQLite database — the same
``httpx.AsyncClient`` + ``ASGITransport`` setup the rest of the suite uses.
"""

import pytest
from httpx import AsyncClient

from src.permission import service as permission_service
from src.permission.models import CasbinRule, Role, UserRole

ROLES_URL = "/api/v1/permission/roles"


async def _user_id(client: AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def test_listing_roles_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(ROLES_URL)
    assert response.status_code == 401
    assert response.json()["code"] == "token_invalid"


async def test_user_without_roles_is_forbidden(
    client: AsyncClient, member_token: str, api_client
) -> None:
    member = api_client(member_token)
    response = await member.get(ROLES_URL)
    assert response.status_code == 403
    assert response.json()["code"] == "access_denied"


async def test_admin_lists_the_seeded_roles(
    client: AsyncClient, admin_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    response = await admin.get(ROLES_URL)
    assert response.status_code == 200, response.text

    body = response.json()
    names = {role["name"] for role in body}
    assert {"admin", "editor", "reader"} <= names

    admin_role = next(role for role in body if role["name"] == "admin")
    assert any(
        permission["obj"] == "/api/v1/permission/*" for permission in admin_role["permissions"]
    )


async def test_admin_creates_and_reads_a_role(
    client: AsyncClient, admin_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    response = await admin.post(ROLES_URL, json={"name": "auditor", "description": "Reads roles."})
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "auditor"

    response = await admin.get(f"{ROLES_URL}/auditor")
    assert response.status_code == 200
    assert response.json()["description"] == "Reads roles."


async def test_creating_the_same_role_twice_conflicts(
    client: AsyncClient, admin_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    payload = {"name": "auditor"}
    assert (await admin.post(ROLES_URL, json=payload)).status_code == 201

    response = await admin.post(ROLES_URL, json=payload)
    assert response.status_code == 409
    assert response.json()["code"] == "role_already_exists"


async def test_unknown_role_returns_404(client: AsyncClient, admin_token: str, api_client) -> None:
    admin = api_client(admin_token)
    response = await admin.get(f"{ROLES_URL}/ghost")
    assert response.status_code == 404
    assert response.json()["code"] == "role_not_found"


async def test_granted_permission_lets_a_plain_user_read_roles(
    client: AsyncClient, admin_token: str, member_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    member = api_client(member_token)

    assert (await member.get(ROLES_URL)).status_code == 403

    assert (await admin.post(ROLES_URL, json={"name": "auditor"})).status_code == 201
    granted = await admin.put(
        f"{ROLES_URL}/auditor/permissions",
        json={"obj": "/api/v1/permission/roles", "act": "GET"},
    )
    assert granted.status_code == 200, granted.text

    user_id = await _user_id(client, member_token)
    assigned = await admin.put(f"/api/v1/permission/users/{user_id}/roles/auditor")
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["roles"] == ["auditor"]

    response = await member.get(ROLES_URL)
    assert response.status_code == 200, response.text


async def test_revoking_the_permission_takes_the_access_away(
    client: AsyncClient, admin_token: str, member_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    member = api_client(member_token)

    await admin.post(ROLES_URL, json={"name": "auditor"})
    granted = await admin.put(
        f"{ROLES_URL}/auditor/permissions",
        json={"obj": "/api/v1/permission/roles", "act": "GET"},
    )
    permission_id = granted.json()["id"]

    user_id = await _user_id(client, member_token)
    await admin.put(f"/api/v1/permission/users/{user_id}/roles/auditor")
    assert (await member.get(ROLES_URL)).status_code == 200

    revoked = await admin.delete(f"{ROLES_URL}/auditor/permissions/{permission_id}")
    assert revoked.status_code == 204

    assert (await member.get(ROLES_URL)).status_code == 403


async def test_revoking_the_role_takes_the_access_away(
    client: AsyncClient, admin_token: str, member_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    member = api_client(member_token)

    await admin.post(ROLES_URL, json={"name": "auditor"})
    await admin.put(
        f"{ROLES_URL}/auditor/permissions",
        json={"obj": "/api/v1/permission/roles", "act": "GET"},
    )
    user_id = await _user_id(client, member_token)
    await admin.put(f"/api/v1/permission/users/{user_id}/roles/auditor")
    assert (await member.get(ROLES_URL)).status_code == 200

    revoked = await admin.delete(f"/api/v1/permission/users/{user_id}/roles/auditor")
    assert revoked.status_code == 204

    assert (await member.get(ROLES_URL)).status_code == 403


async def test_listing_the_roles_of_a_user(
    client: AsyncClient, admin_token: str, member_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    user_id = await _user_id(client, member_token)

    response = await admin.get(f"/api/v1/permission/users/{user_id}/roles")
    assert response.status_code == 200
    assert response.json() == {"user_id": user_id, "roles": []}


async def test_the_admin_role_cannot_be_deleted(
    client: AsyncClient, admin_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    response = await admin.delete(f"{ROLES_URL}/admin")
    assert response.status_code == 409
    assert response.json()["code"] == "admin_role_protected"


async def test_deleting_a_role_removes_its_permissions_and_assignments(
    client: AsyncClient, admin_token: str, member_token: str, api_client, session_factory
) -> None:
    admin = api_client(admin_token)
    member = api_client(member_token)

    await admin.post(ROLES_URL, json={"name": "auditor"})
    await admin.put(
        f"{ROLES_URL}/auditor/permissions",
        json={"obj": "/api/v1/permission/roles", "act": "GET"},
    )
    user_id = await _user_id(client, member_token)
    await admin.put(f"/api/v1/permission/users/{user_id}/roles/auditor")

    assert (await admin.delete(f"{ROLES_URL}/auditor")).status_code == 204

    async with session_factory() as session:
        assert await session.get(Role, "auditor") is None
        assignments = await session.execute(
            UserRole.__table__.select().where(UserRole.role_name == "auditor")
        )
        assert assignments.all() == []
        policies = await session.execute(
            CasbinRule.__table__.select().where(CasbinRule.v0 == "auditor")
        )
        assert policies.all() == []

    assert (await member.get(ROLES_URL)).status_code == 403


async def test_granting_the_same_permission_twice_is_a_no_op(
    client: AsyncClient, admin_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    await admin.post(ROLES_URL, json={"name": "auditor"})

    first = await admin.put(
        f"{ROLES_URL}/auditor/permissions",
        json={"obj": "/api/v1/permission/roles", "act": "GET"},
    )
    second = await admin.put(
        f"{ROLES_URL}/auditor/permissions",
        json={"obj": "/api/v1/permission/roles", "act": "GET"},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


async def test_assigning_a_role_twice_is_a_no_op(
    client: AsyncClient, admin_token: str, member_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    user_id = await _user_id(client, member_token)

    first = await admin.put(f"/api/v1/permission/users/{user_id}/roles/reader")
    second = await admin.put(f"/api/v1/permission/users/{user_id}/roles/reader")
    assert first.status_code == second.status_code == 200
    assert second.json()["roles"] == ["reader"]


async def test_revoking_a_role_the_user_does_not_hold_returns_404(
    client: AsyncClient, admin_token: str, member_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    user_id = await _user_id(client, member_token)

    response = await admin.delete(f"/api/v1/permission/users/{user_id}/roles/reader")
    assert response.status_code == 404
    assert response.json()["code"] == "user_role_not_found"


async def test_assigning_an_unknown_role_returns_404(
    client: AsyncClient, admin_token: str, member_token: str, api_client
) -> None:
    admin = api_client(admin_token)
    user_id = await _user_id(client, member_token)

    response = await admin.put(f"/api/v1/permission/users/{user_id}/roles/ghost")
    assert response.status_code == 404
    assert response.json()["code"] == "role_not_found"


@pytest.mark.parametrize(
    "obj",
    [
        "/api/v1/permission/roles",
        "/api/v1/permission/roles/*",
        "/api/v1/permission/users/*/roles",
    ],
)
async def test_the_admin_role_covers_the_permission_namespace(session_factory, obj: str) -> None:
    """The Casbin matcher resolves the path patterns the routes declare."""
    from src.permission.enforcer import build_enforcer

    async with session_factory() as session:
        await permission_service.seed(session)
        enforcer = await build_enforcer(session)
        assert enforcer.enforce("admin", obj, "GET") is True
        assert enforcer.enforce("admin", obj, "DELETE") is True
        assert enforcer.enforce("editor", obj, "GET") is False
        assert enforcer.enforce("reader", obj, "GET") is False
