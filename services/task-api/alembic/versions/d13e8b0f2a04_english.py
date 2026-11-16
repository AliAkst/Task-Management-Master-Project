"""Ingilizce kocu tablolari: profil, hata gunlugu, kelime (SM-2), seanslar (Faz 13j1)

Revision ID: d13e8b0f2a04
Revises: c13d7a9e1f03
Create Date: 2026-11-16 03:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.entities.base import UTCDateTime

revision: str = "d13e8b0f2a04"
down_revision: str | None = "c13d7a9e1f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "english_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("target_level", sa.String(length=2), nullable=False),
        sa.Column("current_level", sa.String(length=2), nullable=True),
        sa.Column("daily_minutes", sa.SmallInteger(), nullable=False),
        sa.Column("focus", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.Date(), nullable=False),
        sa.Column("created_at", UTCDateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "english_mistakes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("original", sa.Text(), nullable=False),
        sa.Column("corrected", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("explanation_tr", sa.Text(), nullable=True),
        sa.Column("review_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_english_mistakes_user_id", "english_mistakes", ["user_id"])
    op.create_index("ix_english_mistakes_created_at", "english_mistakes", ["created_at"])

    op.create_table(
        "english_vocab",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=100), nullable=False),
        sa.Column("term_key", sa.String(length=100), nullable=False),
        sa.Column("meaning_tr", sa.String(length=300), nullable=False),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("ease", sa.Float(), server_default="2.5", nullable=False),
        sa.Column("interval_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lapses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("last_reviewed_at", UTCDateTime(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "term_key"),
    )
    op.create_index("ix_english_vocab_user_id", "english_vocab", ["user_id"])
    op.create_index("ix_english_vocab_due_on", "english_vocab", ["due_on"])

    op.create_table(
        "english_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("started_at", UTCDateTime(), nullable=False),
        sa.Column("minutes", sa.SmallInteger(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("new_vocab", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("mistakes_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_english_sessions_user_id", "english_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_english_sessions_user_id", table_name="english_sessions")
    op.drop_table("english_sessions")
    op.drop_index("ix_english_vocab_due_on", table_name="english_vocab")
    op.drop_index("ix_english_vocab_user_id", table_name="english_vocab")
    op.drop_table("english_vocab")
    op.drop_index("ix_english_mistakes_created_at", table_name="english_mistakes")
    op.drop_index("ix_english_mistakes_user_id", table_name="english_mistakes")
    op.drop_table("english_mistakes")
    op.drop_table("english_profiles")
