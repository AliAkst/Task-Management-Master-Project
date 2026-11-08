"""card series for recurring cards

Revision ID: c3e8f1a5d7b4
Revises: b8d4f6a2c9e1
Create Date: 2026-11-08 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3e8f1a5d7b4"
down_revision: str | None = "b8d4f6a2c9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "card_series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("recurrence_rule", sa.String(length=500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_card_series_user_id", "card_series", ["user_id"])
    op.create_index("ix_card_series_board_id", "card_series", ["board_id"])
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("series_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("series_index", sa.Integer(), nullable=True))
        batch.create_index("ix_tasks_series_id", ["series_id"])
        batch.create_foreign_key(
            "fk_tasks_series_id",
            "card_series",
            ["series_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("fk_tasks_series_id", type_="foreignkey")
        batch.drop_index("ix_tasks_series_id")
        batch.drop_column("series_index")
        batch.drop_column("series_id")
    op.drop_index("ix_card_series_board_id", table_name="card_series")
    op.drop_index("ix_card_series_user_id", table_name="card_series")
    op.drop_table("card_series")
