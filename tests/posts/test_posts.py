"""Posts domain tests."""

import uuid

from httpx import AsyncClient

POST_PAYLOAD = {"title": "Hello", "content": "World", "status": "published"}


async def test_create_post_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/posts", json=POST_PAYLOAD)

    assert response.status_code == 401


async def test_create_post_as_author(auth_client: AsyncClient) -> None:
    response = await auth_client.post("/api/v1/posts", json=POST_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Hello"
    assert body["view_count"] == 0
    assert body["status"] == "published"


async def test_list_posts_is_paginated(auth_client: AsyncClient) -> None:
    for index in range(3):
        await auth_client.post("/api/v1/posts", json={**POST_PAYLOAD, "title": f"Post {index}"})

    response = await auth_client.get("/api/v1/posts", params={"page": 1, "page_size": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


async def test_list_posts_filters_by_status(auth_client: AsyncClient) -> None:
    await auth_client.post("/api/v1/posts", json={**POST_PAYLOAD, "status": "draft"})
    await auth_client.post("/api/v1/posts", json=POST_PAYLOAD)

    response = await auth_client.get("/api/v1/posts", params={"status": "draft"})

    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_get_post_by_id(auth_client: AsyncClient) -> None:
    created = await auth_client.post("/api/v1/posts", json=POST_PAYLOAD)
    post_id = created.json()["id"]

    response = await auth_client.get(f"/api/v1/posts/{post_id}")

    assert response.status_code == 200
    assert response.json()["id"] == post_id


async def test_get_missing_post_returns_404(auth_client: AsyncClient) -> None:
    response = await auth_client.get(f"/api/v1/posts/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "post_not_found"


async def test_author_can_update_their_post(auth_client: AsyncClient) -> None:
    created = await auth_client.post("/api/v1/posts", json=POST_PAYLOAD)
    post_id = created.json()["id"]

    response = await auth_client.patch(f"/api/v1/posts/{post_id}", json={"title": "Updated"})

    assert response.status_code == 200
    assert response.json()["title"] == "Updated"


async def test_non_author_cannot_update_a_post(auth_client: AsyncClient, signup_user) -> None:
    created = await auth_client.post("/api/v1/posts", json=POST_PAYLOAD)
    post_id = created.json()["id"]

    token = await signup_user(auth_client, "mallory@example.com", "mallory")

    response = await auth_client.patch(
        f"/api/v1/posts/{post_id}",
        json={"title": "Hijacked"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "not_post_owner"


async def test_author_can_delete_their_post(auth_client: AsyncClient) -> None:
    created = await auth_client.post("/api/v1/posts", json=POST_PAYLOAD)
    post_id = created.json()["id"]

    response = await auth_client.delete(f"/api/v1/posts/{post_id}")

    assert response.status_code == 204
    assert (await auth_client.get(f"/api/v1/posts/{post_id}")).status_code == 404


async def test_view_counter_increments(auth_client: AsyncClient) -> None:
    created = await auth_client.post("/api/v1/posts", json=POST_PAYLOAD)
    post_id = created.json()["id"]

    for _ in range(3):
        response = await auth_client.post(f"/api/v1/posts/{post_id}/views")
        assert response.status_code == 200

    fetched = await auth_client.get(f"/api/v1/posts/{post_id}")
    assert fetched.json()["view_count"] == 3


async def test_archived_post_cannot_be_updated(auth_client: AsyncClient) -> None:
    created = await auth_client.post("/api/v1/posts", json={**POST_PAYLOAD, "status": "archived"})
    post_id = created.json()["id"]

    response = await auth_client.patch(f"/api/v1/posts/{post_id}", json={"title": "Updated"})

    assert response.status_code == 409
    assert response.json()["code"] == "post_archived"
