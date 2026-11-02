"""Casbin enforcer construction and the per-request authorization pipeline.

Two storage rules shape this module:

* **Permissions** (``p`` policies) live in the ``casbin_rule`` table and are
  loaded by the adapter.
* **Role membership** (``g`` policies) lives in the ``user_role`` table and is
  injected into the enforcer's in-memory model on every request. It is never
  written to ``casbin_rule``, so there is a single source of truth for "who
  holds which role" and no chance of the two disagreeing.
"""

import uuid
from functools import lru_cache
from importlib import resources
from pathlib import Path

import casbin
from casbin.model import Model
from casbin_async_sqlalchemy_adapter import Adapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import engine
from src.permission.config import permission_settings
from src.permission.models import CasbinRule, UserRole

MODEL_PACKAGE = "src.permission"
MODEL_FILENAME = "model.conf"


@lru_cache
def get_model_text() -> str:
    """Return the Casbin model definition, read once per process."""
    configured = permission_settings.MODEL_PATH
    if configured:
        return Path(configured).read_text(encoding="utf-8")
    return (resources.files(MODEL_PACKAGE) / MODEL_FILENAME).read_text(encoding="utf-8")


def new_model() -> Model:
    """Create a fresh Casbin model.

    A fresh instance per request is mandatory: ``load_policy`` mutates the
    model it is handed, so sharing one instance across concurrent requests
    would race.
    """
    model = Model()
    model.load_model_from_text(get_model_text())
    return model


def create_adapter(session: AsyncSession) -> Adapter:
    """Bind the adapter to the request-scoped session.

    Passing ``db_session`` keeps policy reads and writes inside the caller's
    transaction — the adapter neither commits nor rolls back on its own.

    ``db_class`` points the adapter at our own ``casbin_rule`` model, which is
    what makes the table visible to Alembic. Note that the adapter then
    rewrites its internal ``Base.metadata`` to ours, so
    ``adapter.create_table()`` must never be called: it would create every
    table in the project, not just ``casbin_rule``.
    """
    return Adapter(engine, db_class=CasbinRule, db_session=session)


async def build_enforcer(session: AsyncSession) -> casbin.AsyncEnforcer:
    """Load the persisted ``p`` policies into a fresh enforcer."""
    enforcer = casbin.AsyncEnforcer(new_model(), create_adapter(session))
    await enforcer.load_policy()
    return enforcer


async def list_user_roles(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Return the role names held by ``user_id``."""
    result = await session.execute(select(UserRole.role_name).where(UserRole.user_id == user_id))
    return list(result.scalars().all())


async def build_user_enforcer(session: AsyncSession, user_id: uuid.UUID) -> casbin.AsyncEnforcer:
    """Load the policies *and* the caller's roles, ready to enforce.

    The grouping policies are injected in memory only — auto-save is disabled
    so the adapter never sees them — and the role links are rebuilt
    afterwards because Casbin does not do that on its own when a grouping
    policy is added.
    """
    enforcer = await build_enforcer(session)

    roles = await list_user_roles(session, user_id)
    if roles:
        enforcer.enable_auto_save(False)
        for role in roles:
            await enforcer.add_grouping_policy(str(user_id), role)
        enforcer.build_role_links()

    return enforcer


async def is_allowed(session: AsyncSession, user_id: uuid.UUID, obj: str, act: str) -> bool:
    """Return whether the user may perform ``act`` on ``obj``."""
    enforcer = await build_user_enforcer(session, user_id)
    return enforcer.enforce(str(user_id), obj, act)
