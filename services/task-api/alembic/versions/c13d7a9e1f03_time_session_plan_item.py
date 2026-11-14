"""time_sessions.day_plan_item_id: kartsiz plan maddesine kronometre (Faz 13g)

Revision ID: c13d7a9e1f03
Revises: b13c6f8d0e02
Create Date: 2026-11-14 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c13d7a9e1f03"
down_revision: str | None = "b13c6f8d0e02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("time_sessions") as batch:
        batch.add_column(sa.Column("day_plan_item_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_time_sessions_day_plan_item_id",
            "day_plan_items",
            ["day_plan_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_time_sessions_day_plan_item_id", ["day_plan_item_id"])


def downgrade() -> None:
    with op.batch_alter_table("time_sessions") as batch:
        batch.drop_index("ix_time_sessions_day_plan_item_id")
        batch.drop_constraint("fk_time_sessions_day_plan_item_id", type_="foreignkey")
        batch.drop_column("day_plan_item_id")
