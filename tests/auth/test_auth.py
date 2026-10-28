"""Auth domain tests."""

from httpx import AsyncClient

SIGNUP_PAYLOAD = {
    "email": "alice@example.com",
    "username": "alice",
    "password": "sup3r-s3cret",
}


async def test_signup_creates_user_and_returns_tokens(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == 300


async def test_signup_rejects_duplicate_email(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)

    response = await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)

    assert response.status_code == 409
    assert response.json()["code"] == "email_taken"


async def test_signup_rejects_weak_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup", json={**SIGNUP_PAYLOAD, "password": "short"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_login_with_valid_credentials(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": SIGNUP_PAYLOAD["email"], "password": SIGNUP_PAYLOAD["password"]},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_accepts_a_username_instead_of_an_email(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": SIGNUP_PAYLOAD["username"], "password": SIGNUP_PAYLOAD["password"]},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_with_wrong_password(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": SIGNUP_PAYLOAD["email"], "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


async def test_login_requires_form_fields(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/login", data={"username": "alice"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["details"]


async def test_me_requires_a_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_me_returns_the_authenticated_user(client: AsyncClient) -> None:
    signup = await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)
    token = signup.json()["access_token"]

    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == SIGNUP_PAYLOAD["email"]
    assert body["username"] == SIGNUP_PAYLOAD["username"]
    assert "password_hash" not in body


async def test_refresh_rotates_the_token_pair(client: AsyncClient) -> None:
    signup = await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)
    refresh_token = signup.json()["refresh_token"]

    response = await client.post("/api/v1/auth/refresh", data={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_refresh_reads_the_cookie(client: AsyncClient) -> None:
    signup = await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)
    refresh_token = signup.json()["refresh_token"]
    client.cookies.set("refresh_token", refresh_token)

    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_refresh_rejects_an_access_token(client: AsyncClient) -> None:
    signup = await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)
    access_token = signup.json()["access_token"]

    response = await client.post("/api/v1/auth/refresh", data={"refresh_token": access_token})

    assert response.status_code == 401
    assert response.json()["code"] == "token_invalid"


async def test_refresh_requires_a_token(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/refresh", data={})

    assert response.status_code == 401
    assert response.json()["code"] == "refresh_token_required"
