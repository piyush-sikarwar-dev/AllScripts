"""ORM models for the app's own database (CLAUDE.md §5).

audit_log and release_log are append-only: there are no update/delete code paths for them.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.app import Base

# Postgres types with portable fallbacks for the SQLite unit-test database.
JsonB = JSON().with_variant(JSONB(), "postgresql")
TextArray = JSON().with_variant(ARRAY(Text()), "postgresql")
BigId = BigInteger().with_variant(Integer(), "sqlite")  # SQLite autoincrement needs INTEGER


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    __tablename__ = "sessions"

    # SHA-256 (hex) of the random session token; the token itself is never stored.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(400))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    patient_key: Mapped[str | None] = mapped_column(String(32), index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JsonB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(45))
    request_id: Mapped[str | None] = mapped_column(String(64))


class ReleaseLog(Base):
    __tablename__ = "release_log"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    patient_key: Mapped[str] = mapped_column(String(32), index=True)
    sections: Mapped[list[str]] = mapped_column(TextArray)
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    recipient: Mapped[str] = mapped_column(String(300))
    page_count: Mapped[int] = mapped_column(Integer)
    file_sha256: Mapped[str] = mapped_column(String(64))
    release_code: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    purpose: Mapped[str | None] = mapped_column(String(40))


class PatientCrosswalk(Base):
    __tablename__ = "patient_crosswalk"

    patient_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    emr_id: Mapped[int | None] = mapped_column(Integer, index=True)
    ntier_id: Mapped[int | None] = mapped_column(Integer, index=True)
    dmz_id: Mapped[int | None] = mapped_column(Integer, index=True)
    match_method: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Float)
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExportSelection(Base):
    """Visits picked with "Add to export" for the next PDF; removed with the session."""

    __tablename__ = "export_selection"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "patient_key", "item_type", "item_id", name="uq_export_selection_item"
        ),
        Index("ix_export_selection_session_patient", "session_id", "patient_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    patient_key: Mapped[str] = mapped_column(String(32))
    item_type: Mapped[str] = mapped_column(String(16))
    item_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
