"""Shared fixtures for the permission domain tests."""

from collections.abc import AsyncIterator, Callable

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.permission import service as permission_service
from src.permission.config import permission_settings

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "sup3r-s3cret"


@pytest.fixture
def seeded_admin_password(monkeypatch) -> str:
    """Pin the password the seed gives the admin account."""
    monkeypatch.setattr(permission_settings, "SEED_ADMIN_PASSWORD", ADMIN_PASSWORD)
    return ADMIN_PASSWORD


@pytest.fixture
async def seeded_roles(session_factory, seeded_admin_password) -> None:
    """Create the default roles, policies and the admin account."""
    async with session_factory() as session:
        await permission_service.seed(session)


@pytest.fixture
async def admin_token(client, seeded_roles) -> str:
    """Sign in as the seeded admin and return its access token."""
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
async def member_token(client, signup_user) -> str:
    """Register a user without any role and return its access token."""
    return await signup_user(client, "member@example.com", "member")


@pytest.fixture
async def api_client(client) -> AsyncIterator[Callable[[str], AsyncClient]]:
    """Return a factory that builds an HTTP client for a given bearer token.

    The database dependency is already swapped out by the ``client`` fixture,
    so the extra clients hit the same in-memory database.
    """
    created: list[AsyncClient] = []

    def _build(token: str) -> AsyncClient:
        http_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        http_client.headers["Authorization"] = f"Bearer {token}"
        created.append(http_client)
        return http_client

    yield _build

    for http_client in created:
        await http_client.aclose()
