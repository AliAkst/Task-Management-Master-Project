"""event meeting_url (Teams toplanti baglantisi, Faz 8d)

Revision ID: b6d2f8a4c1e9
Revises: a5c9e1b3d7f2
Create Date: 2026-11-09 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b6d2f8a4c1e9"
down_revision: str | None = "a5c9e1b3d7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.add_column(sa.Column("meeting_url", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.drop_column("meeting_url")
