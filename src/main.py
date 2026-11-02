"""FastAPI application factory, lifespan and router wiring."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.auth.config import auth_settings
from src.auth.models import User  # noqa: F401  (registers the `user` table on Base.metadata)
from src.auth.router import router as auth_router
from src.config import API_PREFIX, settings
from src.database import Base, SessionFactory, engine
from src.exceptions import register_exception_handlers
from src.permission import service as permission_service
from src.permission.config import permission_settings
from src.permission.models import (  # noqa: F401  (registers the permission tables)
    CasbinRule,
    Role,
    UserRole,
)
from src.permission.router import router as permission_router
from src.posts.models import Post  # noqa: F401  (registers the `post` table on Base.metadata)
from src.posts.router import router as posts_router

SHOW_DOCS_IN = {"local", "dev", "development", "staging"}

_INSECURE_SECRETS = {
    "JWT_SECRET": "dev-insecure-access-secret-change-me",
    "REFRESH_TOKEN_KEY": "dev-insecure-refresh-key-change-me",
}


def _assert_secrets_configured() -> None:
    """Refuse to boot outside local with the placeholder secrets."""
    if settings.is_local:
        return
    for field, placeholder in _INSECURE_SECRETS.items():
        if getattr(auth_settings, field) == placeholder:
            raise RuntimeError(
                f"AuthConfig.{field} is still the development placeholder. "
                f"Set the AUTH_{field} environment variable before deploying."
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create tables locally for a zero-setup dev loop; seed the RBAC defaults."""
    _assert_secrets_configured()
    if settings.is_local and settings.AUTO_CREATE_TABLES:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    if permission_settings.SEED_ENABLED:
        async with SessionFactory() as session:
            await permission_service.seed(session)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    docs_enabled = settings.ENVIRONMENT.lower() in SHOW_DOCS_IN

    app = FastAPI(
        title="FastAPI Reference Application",
        version="0.1.0",
        description="Reference implementation of the fastapi-best-practices ruleset.",
        lifespan=lifespan,
        # `openapi_url=None` disables /docs and /redoc as well.
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)

    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(posts_router, prefix=API_PREFIX)
    app.include_router(permission_router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["ops"], summary="Readiness probe")
    async def ready() -> dict[str, str]:
        return {"status": "ready", "environment": settings.ENVIRONMENT}

    return app


app = create_app()
