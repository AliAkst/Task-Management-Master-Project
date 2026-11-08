"""day plans and items (daily planning + end-of-day review)

Revision ID: f2d6b8a1c4e7
Revises: e7c1a4d8b2f9
Create Date: 2026-11-09 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2d6b8a1c4e7"
down_revision: str | Sequence[str] | None = "e7c1a4d8b2f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "day_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("date", sa.Date(), nullable=False, index=True),
        sa.Column(
            "status",
            sa.Enum("PLANNED", "REVIEWED", name="dayplanstatus"),
            nullable=False,
            server_default="PLANNED",
        ),
        sa.Column("mood", sa.SmallInteger(), nullable=True),
        sa.Column("energy", sa.SmallInteger(), nullable=True),
        sa.Column("reflection", sa.Text(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "date"),
    )
    op.create_table(
        "day_plan_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "day_plan_id",
            sa.Integer(),
            sa.ForeignKey("day_plans.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "card_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=True),
        sa.Column(
            "was_planned", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("planned_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_minutes", sa.Integer(), nullable=True),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "outcome",
            sa.Enum("DONE", "PARTIAL", "NOT_DONE", "POSTPONED", name="itemoutcome"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("tracked_sec", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("postponed_to", sa.Date(), nullable=True, index=True),
        *_timestamps(),
    )


def downgrade() -> None:
    op.drop_table("day_plan_items")
    op.drop_table("day_plans")
    sa.Enum(name="itemoutcome").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="dayplanstatus").drop(op.get_bind(), checkfirst=True)
