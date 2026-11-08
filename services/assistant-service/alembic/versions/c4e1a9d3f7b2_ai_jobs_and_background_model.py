"""ai_jobs and background model preference

Revision ID: c4e1a9d3f7b2
Revises: 8dc696114cab
Create Date: 2026-11-08 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4e1a9d3f7b2"
down_revision: str | None = "8dc696114cab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("target_date", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("action_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_jobs_user_id", "ai_jobs", ["user_id"])
    op.create_index("ix_ai_jobs_target_date", "ai_jobs", ["target_date"])
    with op.batch_alter_table("model_prefs") as batch:
        batch.add_column(
            sa.Column("background_model_id", sa.String(length=200), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("model_prefs") as batch:
        batch.drop_column("background_model_id")
    op.drop_index("ix_ai_jobs_target_date", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_user_id", table_name="ai_jobs")
    op.drop_table("ai_jobs")
