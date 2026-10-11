"""Initial app schema: users, sessions, audit_log, release_log, patient_crosswalk.

Revision ID: 0001
Revises:
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", TS, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", TS, nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_seen_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(400), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("at", TS, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("patient_key", sa.String(32), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_patient_key", "audit_log", ["patient_key"])

    op.create_table(
        "release_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("at", TS, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("patient_key", sa.String(32), nullable=False),
        sa.Column("sections", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("recipient", sa.String(300), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
    )
    op.create_index("ix_release_log_at", "release_log", ["at"])
    op.create_index("ix_release_log_patient_key", "release_log", ["patient_key"])

    op.create_table(
        "patient_crosswalk",
        sa.Column("patient_key", sa.String(32), primary_key=True),
        sa.Column("emr_id", sa.Integer(), nullable=True),
        sa.Column("ntier_id", sa.Integer(), nullable=True),
        sa.Column("dmz_id", sa.Integer(), nullable=True),
        sa.Column("match_method", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("built_at", TS, nullable=False),
    )
    op.create_index("ix_patient_crosswalk_emr_id", "patient_crosswalk", ["emr_id"])
    op.create_index("ix_patient_crosswalk_ntier_id", "patient_crosswalk", ["ntier_id"])
    op.create_index("ix_patient_crosswalk_dmz_id", "patient_crosswalk", ["dmz_id"])

    # Audit and release logs are append-only: the database itself refuses UPDATE / DELETE.
    op.execute(
        "CREATE FUNCTION forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END $$"
    )
    for table in ("audit_log", "release_log"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_change()"
        )


def downgrade() -> None:
    for table in ("audit_log", "release_log"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS forbid_change()")
    for table in ("patient_crosswalk", "release_log", "audit_log", "sessions", "users"):
        op.drop_table(table)
