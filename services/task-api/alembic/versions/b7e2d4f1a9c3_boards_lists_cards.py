"""boards, lists, card fields, notes, checklist, labels, activity_log

Revision ID: b7e2d4f1a9c3
Revises: a1f3c9d2e4b7
Create Date: 2026-11-08 12:00:00

Mevcut task'lar her kullanici icin olusturulan "Genel" board'una, durumlarina
gore Yapilacak / Yapiliyor / Tamamlandi listelerine tasinir.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "b7e2d4f1a9c3"
down_revision: str | Sequence[str] | None = "a1f3c9d2e4b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def _user_fk() -> sa.Column:
    return sa.Column(
        "user_id",
        sa.Integer(),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def upgrade() -> None:
    op.create_table(
        "boards",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scope_description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(20), nullable=False, server_default="#64748b"),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("weekly_time_budget_min", sa.Integer(), nullable=True),
        sa.Column(
            "privacy",
            sa.Enum("CLOUD_ALLOWED", "LOCAL_ONLY", name="boardprivacy"),
            nullable=False,
            server_default="CLOUD_ALLOWED",
        ),
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        *_timestamps(),
    )
    op.create_table(
        "board_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk(),
        sa.Column(
            "board_id",
            sa.Integer(),
            sa.ForeignKey("boards.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "is_done_list", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        *_timestamps(),
    )
    op.create_table(
        "labels",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk(),
        sa.Column(
            "board_id",
            sa.Integer(),
            sa.ForeignKey("boards.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("color", sa.String(20), nullable=False, server_default="#64748b"),
        *_timestamps(),
    )

    with op.batch_alter_table("tasks") as batch:
        batch.alter_column(
            "description",
            existing_type=sa.String(1000),
            type_=sa.Text(),
            existing_nullable=True,
        )
        batch.add_column(sa.Column("board_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("list_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("position", sa.Float(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("start_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("estimated_minutes", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "is_archived", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(
            sa.Column(
                "created_by", sa.String(20), nullable=False, server_default="user"
            )
        )
        batch.create_foreign_key(
            "fk_tasks_board_id", "boards", ["board_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_foreign_key(
            "fk_tasks_list_id", "board_lists", ["list_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_tasks_board_id", ["board_id"])
        batch.create_index("ix_tasks_list_id", ["list_id"])

    op.create_table(
        "card_labels",
        sa.Column(
            "card_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "label_id",
            sa.Integer(),
            sa.ForeignKey("labels.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "card_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk(),
        sa.Column(
            "card_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "checklist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk(),
        sa.Column(
            "card_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk(),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=True, index=True),
        sa.Column("card_id", sa.Integer(), nullable=True, index=True),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("actor", sa.String(20), nullable=False, server_default="user"),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, index=True
        ),
    )

    _migrate_existing_tasks()


def _migrate_existing_tasks() -> None:
    """Mevcut task'lari kullanici basina bir 'Genel' board'a tasir."""
    conn = op.get_bind()
    now = datetime.now(UTC)
    user_ids = [
        r[0]
        for r in conn.execute(
            sa.text("SELECT DISTINCT user_id FROM tasks WHERE board_id IS NULL")
        )
    ]
    for user_id in user_ids:
        board_id = conn.execute(
            sa.text(
                "INSERT INTO boards (user_id, name, color, position, privacy, "
                "is_archived, created_at, updated_at) VALUES (:u, 'Genel', "
                "'#64748b', 1024, 'CLOUD_ALLOWED', :f, :n, :n) RETURNING id"
            ),
            {"u": user_id, "n": now, "f": False},
        ).scalar_one()

        list_ids: dict[str, int] = {}
        for i, (status, name, is_done) in enumerate(
            [
                ("PENDING", "Yapılacak", False),
                ("IN_PROGRESS", "Yapılıyor", False),
                ("COMPLETED", "Tamamlandı", True),
            ]
        ):
            list_ids[status] = conn.execute(
                sa.text(
                    "INSERT INTO board_lists (user_id, board_id, name, position, "
                    "is_done_list, created_at, updated_at) "
                    "VALUES (:u, :b, :name, :p, :d, :n, :n) RETURNING id"
                ),
                {
                    "u": user_id,
                    "b": board_id,
                    "name": name,
                    "p": (i + 1) * 1024,
                    "d": is_done,
                    "n": now,
                },
            ).scalar_one()

        for status, list_id in list_ids.items():
            conn.execute(
                sa.text(
                    "UPDATE tasks SET board_id = :b, list_id = :l, "
                    "position = id * 1024 "
                    "WHERE user_id = :u AND status = :s AND board_id IS NULL"
                ),
                {"b": board_id, "l": list_id, "u": user_id, "s": status},
            )
        conn.execute(
            sa.text(
                "UPDATE tasks SET completed_at = updated_at "
                "WHERE user_id = :u AND status = 'COMPLETED' AND completed_at IS NULL"
            ),
            {"u": user_id},
        )


def downgrade() -> None:
    op.drop_table("activity_log")
    op.drop_table("checklist_items")
    op.drop_table("card_notes")
    op.drop_table("card_labels")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_list_id")
        batch.drop_index("ix_tasks_board_id")
        batch.drop_constraint("fk_tasks_list_id", type_="foreignkey")
        batch.drop_constraint("fk_tasks_board_id", type_="foreignkey")
        for col in (
            "created_by",
            "is_archived",
            "completed_at",
            "estimated_minutes",
            "start_at",
            "position",
            "list_id",
            "board_id",
        ):
            batch.drop_column(col)
        batch.alter_column(
            "description",
            existing_type=sa.Text(),
            type_=sa.String(1000),
            existing_nullable=True,
        )
    op.drop_table("labels")
    op.drop_table("board_lists")
    op.drop_table("boards")
    sa.Enum(name="boardprivacy").drop(op.get_bind(), checkfirst=True)
