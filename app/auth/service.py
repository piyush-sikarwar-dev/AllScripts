"""Credential checks with lockout. Always returns a generic outcome to the caller's UI."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.auth.passwords import dummy_verify, hash_password, needs_rehash, verify_password
from app.repositories.appdb import users
from app.repositories.appdb.models import User

GENERIC_ERROR = "Email or password is incorrect."


@dataclass(frozen=True)
class LoginResult:
    user: User | None  # set only on success
    user_id: int | None  # known account id (for the audit row), even on failure
    reason: str  # "ok" | "unknown_user" | "inactive" | "locked" | "bad_password" (audit only)


def authenticate(db: Session, email: str, password: str) -> LoginResult:
    user = users.get_by_email(db, email) if email.strip() else None
    if user is None:
        dummy_verify(password)
        return LoginResult(None, None, "unknown_user")
    if not user.is_active:
        dummy_verify(password)
        return LoginResult(None, user.id, "inactive")
    if users.is_locked(user):
        dummy_verify(password)
        return LoginResult(None, user.id, "locked")
    if not verify_password(user.password_hash, password):
        users.record_failed_login(db, user)
        return LoginResult(None, user.id, "bad_password")
    if needs_rehash(user.password_hash):
        users.set_password(db, user, hash_password(password))
    users.record_successful_login(db, user)
    return LoginResult(user, user.id, "ok")
