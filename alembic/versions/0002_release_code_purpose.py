"""release_log: add release_code (printed on every PDF page) and purpose.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("release_log", sa.Column("release_code", sa.String(32), nullable=True))
    op.add_column("release_log", sa.Column("purpose", sa.String(40), nullable=True))
    op.create_index("ix_release_log_release_code", "release_log", ["release_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_release_log_release_code", table_name="release_log")
    op.drop_column("release_log", "purpose")
    op.drop_column("release_log", "release_code")
