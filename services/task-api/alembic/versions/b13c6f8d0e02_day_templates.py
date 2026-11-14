"""gun sablonlari, gun override, gun donumu ayari (Faz 13c)

Revision ID: b13c6f8d0e02
Revises: a13b5e7c9d01
Create Date: 2026-11-14 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.entities.base import UTCDateTime

revision: str = "b13c6f8d0e02"
down_revision: str | None = "a13b5e7c9d01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "day_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("weekdays", sa.JSON(), nullable=False),
        sa.Column("blocks", sa.JSON(), nullable=False),
        sa.Column("day_start", sa.Time(), server_default="08:00:00", nullable=False),
        sa.Column("day_end", sa.Time(), server_default="23:00:00", nullable=False),
        sa.Column("buffer_min", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("created_at", UTCDateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index("ix_day_templates_user_id", "day_templates", ["user_id"])

    with op.batch_alter_table("day_plans") as batch:
        batch.add_column(sa.Column("template_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "template_off", sa.Boolean(), server_default="0", nullable=False
            )
        )
        batch.add_column(
            sa.Column("template_applied_at", UTCDateTime(), nullable=True)
        )
        batch.create_foreign_key(
            "fk_day_plans_template_id",
            "day_templates",
            ["template_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("day_plan_items") as batch:
        batch.add_column(sa.Column("source", sa.String(length=20), nullable=True))

    with op.batch_alter_table("user_settings") as batch:
        batch.add_column(
            sa.Column(
                "day_rollover", sa.Time(), server_default="04:00:00", nullable=False
            )
        )
        batch.add_column(sa.Column("morning_time", sa.Time(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_column("morning_time")
        batch.drop_column("day_rollover")

    with op.batch_alter_table("day_plan_items") as batch:
        batch.drop_column("source")

    with op.batch_alter_table("day_plans") as batch:
        batch.drop_constraint("fk_day_plans_template_id", type_="foreignkey")
        batch.drop_column("template_applied_at")
        batch.drop_column("template_off")
        batch.drop_column("template_id")

    op.drop_index("ix_day_templates_user_id", table_name="day_templates")
    op.drop_table("day_templates")
