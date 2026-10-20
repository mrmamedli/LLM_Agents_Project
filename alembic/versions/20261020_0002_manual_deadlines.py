"""Allow manually created deadlines.

Revision ID: 20261020_0002
Revises: 20261018_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0002"
down_revision: str | None = "20261018_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deadlines",
        sa.Column("is_manual", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("deadlines", "file_id", existing_type=sa.Uuid(), nullable=True)
    op.alter_column("deadlines", "source_page", existing_type=sa.Integer(), nullable=True)
    op.alter_column("deadlines", "source_quote", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM deadlines WHERE file_id IS NULL")
    op.execute("UPDATE deadlines SET source_page = 1 WHERE source_page IS NULL")
    op.execute("UPDATE deadlines SET source_quote = '' WHERE source_quote IS NULL")
    op.alter_column("deadlines", "source_quote", existing_type=sa.Text(), nullable=False)
    op.alter_column("deadlines", "source_page", existing_type=sa.Integer(), nullable=False)
    op.alter_column("deadlines", "file_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("deadlines", "is_manual")
