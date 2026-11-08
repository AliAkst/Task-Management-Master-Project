"""card attachments (kart ekleri, Faz 8c)

Revision ID: a5c9e1b3d7f2
Revises: e4b8c2f6a9d3
Create Date: 2026-11-09 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a5c9e1b3d7f2"
down_revision: str | None = "e4b8c2f6a9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "card_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("note_id", sa.Integer(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=80), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["card_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["note_id"], ["card_notes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_card_attachments_user_id", "card_attachments", ["user_id"])
    op.create_index("ix_card_attachments_card_id", "card_attachments", ["card_id"])


def downgrade() -> None:
    op.drop_index("ix_card_attachments_card_id", table_name="card_attachments")
    op.drop_index("ix_card_attachments_user_id", table_name="card_attachments")
    op.drop_table("card_attachments")
