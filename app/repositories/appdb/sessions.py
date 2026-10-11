"""Server-side sessions. Only the SHA-256 of the token is stored."""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.repositories.appdb import as_utc, utcnow
from app.repositories.appdb.models import User, UserSession

IDLE_TIMEOUT = timedelta(minutes=15)
ABSOLUTE_TIMEOUT = timedelta(hours=8)
# Avoid a DB write on every request: only bump last_seen_at when it is this stale.
TOUCH_INTERVAL = timedelta(seconds=60)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create(db: Session, user: User, *, ip: str | None, user_agent: str | None) -> str:
    """Create a session and return the raw token (goes into the cookie, never stored)."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        UserSession(
            id=token_hash(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + ABSOLUTE_TIMEOUT,
            ip=ip,
            user_agent=(user_agent or "")[:400] or None,
        )
    )
    db.commit()
    return token


def resolve(db: Session, token: str) -> tuple[UserSession, User] | None:
    """Return (session, user) when valid; expired/idle sessions are deleted."""
    session = db.get(UserSession, token_hash(token))
    if session is None:
        return None
    now = utcnow()
    last_seen = as_utc(session.last_seen_at)
    if as_utc(session.expires_at) <= now or last_seen + IDLE_TIMEOUT <= now:
        db.delete(session)
        db.commit()
        return None
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        db.delete(session)
        db.commit()
        return None
    if now - last_seen >= TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return session, user


def delete_token(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.id == token_hash(token)))
    db.commit()


def delete_for_user(db: Session, user_id: int) -> None:
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
    db.commit()
