"""Append-only audit log writes (no update/delete functions on purpose)."""

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.appdb import utcnow
from app.repositories.appdb.models import AuditLog

ACTIONS = frozenset(
    {"login", "logout", "login_failed", "view_patient", "view_tab", "view_document", "export",
     "search", "view_visit", "print_visit", "view_note", "print_note",
     "view_history_entry", "print_history"}
)  # fmt: skip


def insert(
    db: Session,
    *,
    action: str,
    user_id: int | None,
    patient_key: str | None,
    detail: dict[str, Any],
    ip: str | None,
    request_id: str | None,
) -> None:
    if action not in ACTIONS:
        raise ValueError(f"unknown audit action: {action}")
    db.add(
        AuditLog(
            at=utcnow(),
            user_id=user_id,
            action=action,
            patient_key=patient_key,
            detail=detail,
            ip=ip,
            request_id=request_id,
        )
    )
    db.commit()
