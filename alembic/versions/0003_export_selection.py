"""export_selection: visits a user picked with "Add to export" (cleared with the session).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_selection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(64),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("patient_key", sa.String(32), nullable=False),
        sa.Column("item_type", sa.String(16), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "session_id", "patient_key", "item_type", "item_id", name="uq_export_selection_item"
        ),
    )
    op.create_index(
        "ix_export_selection_session_patient", "export_selection", ["session_id", "patient_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_export_selection_session_patient", table_name="export_selection")
    op.drop_table("export_selection")
