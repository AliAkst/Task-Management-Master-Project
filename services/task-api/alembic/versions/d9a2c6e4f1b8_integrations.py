"""integration accounts, external links, inbox board

Revision ID: d9a2c6e4f1b8
Revises: c3e8f1a5d7b4
Create Date: 2026-11-08 23:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9a2c6e4f1b8"
down_revision: str | None = "c3e8f1a5d7b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("account_label", sa.String(length=200), nullable=True),
        sa.Column("tokens_encrypted", sa.Text(), nullable=False),
        sa.Column("scopes", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider"),
    )
    op.create_index(
        "ix_integration_accounts_user_id", "integration_accounts", ["user_id"]
    )
    op.create_table(
        "external_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("external_parent_id", sa.String(length=200), nullable=True),
        sa.Column("etag", sa.String(length=200), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("pending_push", sa.Boolean(), nullable=False),
        sa.Column("push_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", "entity_type", "external_id"),
    )
    op.create_index("ix_external_links_user_id", "external_links", ["user_id"])
    op.create_index(
        "ix_external_links_entity", "external_links", ["entity_type", "entity_id"]
    )
    with op.batch_alter_table("boards") as batch:
        batch.add_column(sa.Column("system_kind", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("boards") as batch:
        batch.drop_column("system_kind")
    op.drop_index("ix_external_links_entity", table_name="external_links")
    op.drop_index("ix_external_links_user_id", table_name="external_links")
    op.drop_table("external_links")
    op.drop_index("ix_integration_accounts_user_id", table_name="integration_accounts")
    op.drop_table("integration_accounts")
