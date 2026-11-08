"""time sessions (stopwatch / manual time entries)

Revision ID: e7c1a4d8b2f9
Revises: d5b9f2c3e6a1
Create Date: 2026-11-08 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7c1a4d8b2f9"
down_revision: str | Sequence[str] | None = "d5b9f2c3e6a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "time_sessions",
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
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("board_id", sa.Integer(), nullable=True, index=True),
        sa.Column("card_title", sa.String(200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="timer"),
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
    )
    # Kullanici basina tek calisan oturum
    op.create_index(
        "uq_time_sessions_one_active_per_user",
        "time_sessions",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("ended_at IS NULL"),
        postgresql_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_time_sessions_one_active_per_user", table_name="time_sessions")
    op.drop_table("time_sessions")
