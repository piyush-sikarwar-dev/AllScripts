"""User accounts (one role; no sign-up — accounts are created with cli.py)."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.repositories.appdb import as_utc, utcnow
from app.repositories.appdb.models import User

MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == normalise_email(email)))


def get(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create(db: Session, *, email: str, full_name: str, password_hash: str) -> User:
    user = User(
        email=normalise_email(email),
        full_name=full_name.strip(),
        password_hash=password_hash,
        is_active=True,
        failed_attempts=0,
    )
    db.add(user)
    db.commit()
    return user


def is_locked(user: User) -> bool:
    locked_until = as_utc(user.locked_until)
    return locked_until is not None and locked_until > utcnow()


def record_failed_login(db: Session, user: User) -> None:
    """Count a failure; on the 5th, lock the account for 15 minutes and reset the counter."""
    user.failed_attempts = (user.failed_attempts or 0) + 1
    if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = utcnow() + LOCKOUT
        user.failed_attempts = 0
    db.commit()


def record_successful_login(db: Session, user: User) -> None:
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    db.commit()


def set_password(db: Session, user: User, password_hash: str) -> None:
    user.password_hash = password_hash
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()


def set_active(db: Session, user: User, active: bool) -> None:
    user.is_active = active
    db.commit()
