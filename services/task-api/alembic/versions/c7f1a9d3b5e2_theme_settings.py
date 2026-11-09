"""tema ayarlari: user_settings.theme/background, boards.background (Faz 8g)

Revision ID: c7f1a9d3b5e2
Revises: b6d2f8a4c1e9
Create Date: 2026-11-09 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7f1a9d3b5e2"
down_revision: str | None = "b6d2f8a4c1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.add_column(
            sa.Column(
                "theme", sa.String(length=10), nullable=False, server_default="system"
            )
        )
        batch.add_column(
            sa.Column(
                "background",
                sa.String(length=20),
                nullable=False,
                server_default="kagit",
            )
        )
    with op.batch_alter_table("boards") as batch:
        batch.add_column(sa.Column("background", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("boards") as batch:
        batch.drop_column("background")
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_column("background")
        batch.drop_column("theme")
