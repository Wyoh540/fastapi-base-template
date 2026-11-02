"""Permission domain ORM models."""

import uuid
from typing import TYPE_CHECKING

from casbin_async_sqlalchemy_adapter import create_casbin_rule_model
from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.auth.models import User  # noqa: F401  (registers the `user` table for FK resolution)
from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    # Type checkers need a class to hang the annotations on; the runtime model
    # below has exactly the same shape.
    from casbin_async_sqlalchemy_adapter import CasbinRule
else:
    # The Casbin policy table.
    #
    # ``create_casbin_rule_model`` is the adapter's own hook for attaching the
    # policy table to *our* declarative base, so Alembic sees it like any
    # other table in this project and the naming convention applies.
    #
    # The table keeps Casbin's native shape (ptype + v0..v5) on purpose: the
    # adapter reads rows through ``str(row)``, which stops at the first NULL,
    # so columns must not be reordered or left with holes. Only ``p`` rows are
    # stored here — role membership lives in ``user_role``.
    CasbinRule = create_casbin_rule_model(Base, "casbin_rule")


class Role(TimestampMixin, Base):
    """A role definition.

    The name is the Casbin policy subject: a policy row
    ``(p, editor, /api/v1/posts/*, GET)`` grants that permission to whoever
    holds the ``editor`` role.
    """

    __tablename__ = "role"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class UserRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Who holds which role.

    This table is the single source of truth for role membership. The Casbin
    ``g`` (grouping) policies are *not* persisted — they are injected into the
    enforcer's in-memory model on every request. See
    :func:`src.permission.enforcer.build_user_enforcer`.
    """

    __tablename__ = "user_role"
    __table_args__ = (
        UniqueConstraint("user_id", "role_name", name="uq_user_role_user_id_role_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    role_name: Mapped[str] = mapped_column(
        String(64), ForeignKey("role.name", ondelete="CASCADE"), index=True
    )
