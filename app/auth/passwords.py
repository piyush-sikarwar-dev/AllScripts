"""Password hashing with argon2id."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 12

_hasher = PasswordHasher()
# Used to spend the same time on unknown emails as on real ones (no user enumeration by timing).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-only")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def dummy_verify(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def password_problem(password: str) -> str | None:
    """Validation message for a new password, or None when acceptable."""
    if len(password) < MIN_LENGTH:
        return f"Password must be at least {MIN_LENGTH} characters."
    if password.strip() != password:
        return "Password must not start or end with spaces."
    return None
