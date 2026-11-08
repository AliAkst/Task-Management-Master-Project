"""oauth clients (arayuzden girilen Google/Microsoft uygulama kimligi)

Revision ID: e4b8c2f6a9d3
Revises: d9a2c6e4f1b8
Create Date: 2026-11-08 23:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e4b8c2f6a9d3"
down_revision: str | None = "d9a2c6e4f1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("client_id", sa.String(length=300), nullable=False),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider"),
    )
    op.create_index("ix_oauth_clients_user_id", "oauth_clients", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_oauth_clients_user_id", table_name="oauth_clients")
    op.drop_table("oauth_clients")
