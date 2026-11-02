"""add permission tables

Revision ID: b7e4a1c93d52
Revises: 886e951c11c5
Create Date: 2026-11-02 22:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e4a1c93d52"
down_revision: str | Sequence[str] | None = "886e951c11c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "role",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name", name=op.f("role_pkey")),
    )
    op.create_table(
        "casbin_rule",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ptype", sa.String(length=255), nullable=True),
        sa.Column("v0", sa.String(length=255), nullable=True),
        sa.Column("v1", sa.String(length=255), nullable=True),
        sa.Column("v2", sa.String(length=255), nullable=True),
        sa.Column("v3", sa.String(length=255), nullable=True),
        sa.Column("v4", sa.String(length=255), nullable=True),
        sa.Column("v5", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("casbin_rule_pkey")),
    )
    op.create_table(
        "user_role",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_name", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["role_name"], ["role.name"], name=op.f("user_role_role_name_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("user_role_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("user_role_pkey")),
        sa.UniqueConstraint("user_id", "role_name", name="uq_user_role_user_id_role_name"),
    )
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("user_role_role_name_idx"), ["role_name"], unique=False)
        batch_op.create_index(batch_op.f("user_role_user_id_idx"), ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("user_role_user_id_idx"))
        batch_op.drop_index(batch_op.f("user_role_role_name_idx"))

    op.drop_table("user_role")
    op.drop_table("casbin_rule")
    op.drop_table("role")
