"""Create initial application tables.

Revision ID: 20261018_0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261018_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("verification_token", sa.String(length=128), nullable=True),
        sa.Column("verification_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("verification_token"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)

    op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subjects_user_id"), "subjects", ["user_id"], unique=False)

    op.create_table(
        "files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("doc_type", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column(
            "summary_key_terms",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(op.f("ix_files_subject_id"), "files", ["subject_id"], unique=False)

    op.create_table(
        "deadlines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("due_date", sa.String(length=64), nullable=True),
        sa.Column("date_note", sa.Text(), nullable=True),
        sa.Column(
            "requirements",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("source_page", sa.Integer(), nullable=False),
        sa.Column("source_quote", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deadlines_file_id"), "deadlines", ["file_id"], unique=False)
    op.create_index(op.f("ix_deadlines_subject_id"), "deadlines", ["subject_id"], unique=False)

    op.create_table(
        "deadline_related_files",
        sa.Column("deadline_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["deadline_id"], ["deadlines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("deadline_id", "file_id"),
    )


def downgrade() -> None:
    op.drop_table("deadline_related_files")
    op.drop_index(op.f("ix_deadlines_subject_id"), table_name="deadlines")
    op.drop_index(op.f("ix_deadlines_file_id"), table_name="deadlines")
    op.drop_table("deadlines")
    op.drop_index(op.f("ix_files_subject_id"), table_name="files")
    op.drop_table("files")
    op.drop_index(op.f("ix_subjects_user_id"), table_name="subjects")
    op.drop_table("subjects")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
