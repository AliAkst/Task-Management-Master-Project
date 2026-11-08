"""ai_insights

Revision ID: d7f2b8c1e4a6
Revises: c4e1a9d3f7b2
Create Date: 2026-11-08 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7f2b8c1e4a6"
down_revision: str | None = "c4e1a9d3f7b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("user_feedback", sa.Text(), nullable=True),
        sa.Column("fact_id", sa.Integer(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_insights_user_id", "ai_insights", ["user_id"])
    op.create_index("ix_ai_insights_key", "ai_insights", ["key"])
    op.create_index("ix_ai_insights_status", "ai_insights", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ai_insights_status", table_name="ai_insights")
    op.drop_index("ix_ai_insights_key", table_name="ai_insights")
    op.drop_index("ix_ai_insights_user_id", table_name="ai_insights")
    op.drop_table("ai_insights")
