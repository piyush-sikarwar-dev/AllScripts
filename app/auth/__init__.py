"""Authentication: passwords, sessions, CSRF and the `current_user` dependency.

Phase 0: fake mode only — no sessions, every visitor is the demo user.
TODO(Phase 2): argon2 passwords, server-side sessions, CSRF, lockout; remove the fake user.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    full_name: str


FAKE_USER = CurrentUser(id=0, email="demo@example.invalid", full_name="Demo User")


def current_user() -> CurrentUser:
    # TODO(Phase 2): read the session cookie; redirect to /login (or HX-Redirect) when missing.
    return FAKE_USER
