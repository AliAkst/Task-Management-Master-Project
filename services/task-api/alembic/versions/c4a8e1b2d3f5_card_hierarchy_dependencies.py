"""card hierarchy (parent_id), dependencies, graph position

Revision ID: c4a8e1b2d3f5
Revises: b7e2d4f1a9c3
Create Date: 2026-11-08 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4a8e1b2d3f5"
down_revision: str | Sequence[str] | None = "b7e2d4f1a9c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("assigned_to", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("graph_x", sa.Float(), nullable=True))
        batch.add_column(sa.Column("graph_y", sa.Float(), nullable=True))
        batch.create_foreign_key(
            "fk_tasks_parent_id", "tasks", ["parent_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_foreign_key(
            "fk_tasks_assigned_to",
            "users",
            ["assigned_to"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_tasks_parent_id", ["parent_id"])

    op.create_table(
        "card_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "card_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "depends_on_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("card_id", "depends_on_id"),
    )


def downgrade() -> None:
    op.drop_table("card_dependencies")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_parent_id")
        batch.drop_constraint("fk_tasks_assigned_to", type_="foreignkey")
        batch.drop_constraint("fk_tasks_parent_id", type_="foreignkey")
        for col in ("graph_y", "graph_x", "assigned_to", "parent_id"):
            batch.drop_column(col)
