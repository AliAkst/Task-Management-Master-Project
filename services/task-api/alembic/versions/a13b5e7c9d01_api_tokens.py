"""kisisel erisim jetonlari: api_tokens (Faz 13b)

Revision ID: a13b5e7c9d01
Revises: c7f1a9d3b5e2
Create Date: 2026-11-14 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.entities.base import UTCDateTime

revision: str = "a13b5e7c9d01"
down_revision: str | None = "c7f1a9d3b5e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hint", sa.String(length=16), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("last_used_at", UTCDateTime(), nullable=True),
        sa.Column("expires_at", UTCDateTime(), nullable=True),
        sa.Column("revoked_at", UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_tokens_user_id", "api_tokens", ["user_id"])
    op.create_index(
        "ix_api_tokens_token_hash", "api_tokens", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_api_tokens_token_hash", table_name="api_tokens")
    op.drop_index("ix_api_tokens_user_id", table_name="api_tokens")
    op.drop_table("api_tokens")
