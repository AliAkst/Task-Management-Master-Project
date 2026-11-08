"""board default model

Revision ID: b8d4f6a2c9e1
Revises: a3c5e7f9b1d2
Create Date: 2026-11-08 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8d4f6a2c9e1"
down_revision: str | Sequence[str] | None = "a3c5e7f9b1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("boards") as batch:
        batch.add_column(
            sa.Column("default_model_id", sa.String(length=200), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("boards") as batch:
        batch.drop_column("default_model_id")
