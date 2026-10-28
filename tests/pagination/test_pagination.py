"""Global pagination module tests."""

from httpx import AsyncClient

from src.config import settings
from src.pagination import PaginationParams, pagination_params


async def test_defaults_are_applied_when_page_size_is_omitted() -> None:
    params = await pagination_params(page=1, page_size=None)

    assert params.page == 1
    assert params.page_size == settings.DEFAULT_PAGE_SIZE


async def test_page_size_is_clamped_to_the_configured_maximum(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "MAX_PAGE_SIZE", 50)

    params = await pagination_params(page=1, page_size=5000)

    assert params.page_size == 50


async def test_offset_and_limit_derive_from_the_window() -> None:
    params = PaginationParams(page=3, page_size=25)

    assert params.offset == 50
    assert params.limit == 25


async def test_endpoint_clamps_an_oversized_page_size(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/posts", params={"page_size": 9999})

    assert response.status_code == 200
    assert response.json()["page_size"] == settings.MAX_PAGE_SIZE


async def test_endpoint_rejects_a_non_positive_page(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/posts", params={"page": 0})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_second_page_returns_the_remaining_rows(auth_client: AsyncClient) -> None:
    for index in range(3):
        await auth_client.post("/api/v1/posts", json={"title": f"Post {index}", "content": "body"})

    first = await auth_client.get("/api/v1/posts", params={"page": 1, "page_size": 2})
    second = await auth_client.get("/api/v1/posts", params={"page": 2, "page_size": 2})

    assert first.json()["total"] == 3
    assert len(first.json()["items"]) == 2
    assert len(second.json()["items"]) == 1
    assert second.json()["page"] == 2
