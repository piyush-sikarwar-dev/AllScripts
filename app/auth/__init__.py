"""Authentication: sessions, CSRF and the `current_user` dependency (CLAUDE.md §8)."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.auth.tokens import (
    SESSION_COOKIE,
    csrf_for_session,
    sign_session,
    tokens_match,
    unsign_session,
)
from app.config import get_settings
from app.db.app import get_db
from app.repositories.appdb import sessions

CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    full_name: str


class LoginRequiredError(Exception):
    """No valid session: full pages redirect to /login, HTMX requests get HX-Redirect."""


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def session_token(request: Request) -> str | None:
    return unsign_session(request.cookies.get(SESSION_COOKIE))


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> CurrentUser:
    token = session_token(request)
    found = sessions.resolve(db, token) if token else None
    if found is None:
        raise LoginRequiredError
    _session, user = found
    current = CurrentUser(id=user.id, email=user.email, full_name=user.full_name)
    request.state.user = current
    request.state.csrf_token = csrf_for_session(token)
    request.state.session_id = sessions.token_hash(token)
    return current


async def require_csrf(request: Request) -> None:
    """Every state-changing request from a signed-in user carries the session's CSRF token."""
    token = session_token(request)
    supplied = request.headers.get(CSRF_HEADER)
    if supplied is None:
        form = await request.form()
        value = form.get(CSRF_FIELD)
        supplied = value if isinstance(value, str) else None
    if token is None or not tokens_match(csrf_for_session(token), supplied):
        raise HTTPException(status_code=403)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(token),
        max_age=int(sessions.ABSOLUTE_TIMEOUT.total_seconds()),
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, secure=get_settings().cookie_secure, samesite="lax", path="/"
    )
