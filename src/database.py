"""Async database engine, session factory and session dependency."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings
from src.models import Base  # noqa: F401  (re-exported for convenience)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped session dependency.

    FastAPI caches the dependency per request, so the same session instance is
    reused across every ``Depends(get_db)`` in a single request.
    """
    async with SessionFactory() as session:
        yield session
