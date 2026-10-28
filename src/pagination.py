"""Global pagination primitives.

Pagination is a cross-cutting concern rather than a domain-specific one, so it
lives beside the shared configuration instead of inside a single bounded
context. Every domain imports it from here::

    from src.pagination import Pagination, PaginatedResponse
"""

from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel, Field

from src.config import settings

T = TypeVar("T")


class PaginationParams(BaseModel):
    """A validated, bounded pagination window."""

    page: int = Field(ge=1, description="1-based page number")
    page_size: int = Field(ge=1, description="Number of items per page")

    @property
    def offset(self) -> int:
        """Number of rows to skip for this page."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope shared by every paginated endpoint."""

    items: list[T]
    total: int
    page: int
    page_size: int


async def pagination_params(
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[int | None, Query(ge=1, description="Items per page")] = None,
) -> PaginationParams:
    """Resolve the requested page window against the configured bounds.

    An oversized ``page_size`` is clamped instead of rejected, so clients can
    ask for "as much as possible" without having to know the limit.
    """
    size = page_size or settings.DEFAULT_PAGE_SIZE
    return PaginationParams(page=page, page_size=min(size, settings.MAX_PAGE_SIZE))


Pagination = Annotated[PaginationParams, Depends(pagination_params)]
