"""Per-session "Add to export" selection (visits and notes for the next PDF release)."""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.repositories.appdb import utcnow
from app.repositories.appdb.models import ExportSelection

VISIT = "visit"


def selected_ids(
    db: Session, session_id: str, patient_key: str, item_type: str = VISIT
) -> set[int]:
    rows = db.scalars(
        select(ExportSelection.item_id).where(
            ExportSelection.session_id == session_id,
            ExportSelection.patient_key == patient_key,
            ExportSelection.item_type == item_type,
        )
    )
    return {int(i) for i in rows}


def toggle(
    db: Session, session_id: str, patient_key: str, item_id: int, item_type: str = VISIT
) -> bool:
    """Add or remove one item; returns True when it is now selected."""
    existing = db.scalar(
        select(ExportSelection).where(
            ExportSelection.session_id == session_id,
            ExportSelection.patient_key == patient_key,
            ExportSelection.item_type == item_type,
            ExportSelection.item_id == item_id,
        )
    )
    if existing is not None:
        db.delete(existing)
        db.commit()
        return False
    db.add(ExportSelection(session_id=session_id, patient_key=patient_key, item_type=item_type,
                           item_id=item_id, added_at=utcnow()))  # fmt: skip
    db.commit()
    return True


def count(db: Session, session_id: str, patient_key: str, item_type: str = VISIT) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ExportSelection)
            .where(
                ExportSelection.session_id == session_id,
                ExportSelection.patient_key == patient_key,
                ExportSelection.item_type == item_type,
            )
        )
        or 0
    )


def count_all(db: Session, session_id: str, patient_key: str) -> int:
    """Items of every type (visits + notes) picked for this patient's next release."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(ExportSelection)
            .where(
                ExportSelection.session_id == session_id,
                ExportSelection.patient_key == patient_key,
            )
        )
        or 0
    )


def clear_session(db: Session, session_id: str) -> None:
    db.execute(delete(ExportSelection).where(ExportSelection.session_id == session_id))
