"""Shared test fixtures.

Tests run against a real SQLite database (in-memory, shared connection) rather
than a mocked one — mocked sessions drift from production behaviour and hide
real SQL errors.
"""

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database import get_db
from src.main import app
from src.models import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def engine():
    """A fresh in-memory database per test, with the schema applied."""
    test_engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    await test_engine.dispose()


@pytest.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:
    """HTTP client bound to the app with the database dependency swapped out."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


@pytest.fixture
def signup_user() -> Callable[[AsyncClient, str, str], Awaitable[str]]:
    """Return a helper that registers a user and hands back their access token."""

    async def _signup(client: AsyncClient, email: str, username: str) -> str:
        response = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "username": username,
                "password": "sup3r-s3cret",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["access_token"]

    return _signup


@pytest.fixture
async def auth_client(client: AsyncClient, signup_user) -> AsyncClient:
    """Client that is already signed in as a fresh user."""
    token = await signup_user(client, "author@example.com", "author")
    client.headers["Authorization"] = f"Bearer {token}"
    return client
