"""Release log (append-only: insert and read, no update/delete paths)."""

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.formatting import clinic_tz
from app.repositories.appdb import utcnow
from app.repositories.appdb.models import ReleaseLog, User


def insert(db: Session, **fields: Any) -> ReleaseLog:
    row = ReleaseLog(at=utcnow(), **fields)
    db.add(row)
    db.commit()
    return row


def page(
    db: Session, *, offset: int, limit: int, date_from: date | None, date_to: date | None
) -> tuple[list[tuple[ReleaseLog, str]], int]:
    """Newest first, with the releasing user's name."""
    query = select(ReleaseLog, User.full_name).join(User, User.id == ReleaseLog.user_id)
    count = select(func.count()).select_from(ReleaseLog)
    if date_from:
        start = datetime.combine(date_from, time.min, tzinfo=clinic_tz())
        query, count = query.where(ReleaseLog.at >= start), count.where(ReleaseLog.at >= start)
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=clinic_tz())
        query, count = query.where(ReleaseLog.at < end), count.where(ReleaseLog.at < end)
    rows = db.execute(query.order_by(ReleaseLog.at.desc(), ReleaseLog.id.desc())
                      .offset(offset).limit(limit)).all()  # fmt: skip
    return [(r[0], r[1]) for r in rows], int(db.scalar(count) or 0)
