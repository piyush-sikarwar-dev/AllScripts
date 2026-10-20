"""Sign-in / sign-out (CLAUDE.md §8)."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth import (
    CSRF_FIELD,
    clear_session_cookie,
    client_ip,
    session_token,
    set_session_cookie,
)
from app.auth.service import GENERIC_ERROR, authenticate
from app.auth.tokens import (
    LOGIN_COOKIE,
    csrf_for_login,
    csrf_for_session,
    new_login_nonce,
    tokens_match,
)
from app.config import get_settings
from app.db.app import get_db
from app.repositories.appdb import sessions
from app.security import login_throttle
from app.templating import render

router = APIRouter()

THROTTLED_ERROR = "Too many sign-in attempts from this computer. Try again in 15 minutes."

Db = Annotated[Session, Depends(get_db)]


def _login_page(request: Request, *, error: str | None, email: str, status: int = 200) -> Response:
    nonce = new_login_nonce()
    response = render(
        request,
        "pages/login.html",
        {"error": error, "email": email, "login_csrf": csrf_for_login(nonce)},
        status_code=status,
    )
    response.set_cookie(
        LOGIN_COOKIE,
        nonce,
        max_age=3600,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/login",
    )
    return response


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Db) -> Response:
    token = session_token(request)
    if token and sessions.resolve(db, token):
        return RedirectResponse("/patients", status_code=303)
    return _login_page(request, error=None, email="")


@router.post("/login")
def login(
    request: Request,
    background: BackgroundTasks,
    db: Db,
    email: Annotated[str, Form(max_length=320)] = "",
    password: Annotated[str, Form(max_length=1024)] = "",
    csrf_token: Annotated[str, Form(alias=CSRF_FIELD, max_length=200)] = "",
) -> Response:
    nonce = request.cookies.get(LOGIN_COOKIE)
    if not nonce or not tokens_match(csrf_for_login(nonce), csrf_token):
        raise HTTPException(status_code=403)

    throttle = login_throttle()
    ip = client_ip(request)
    if throttle.blocked(ip):  # too many failures from this address: the password is not checked
        audit(request, background, "login_failed", detail={"reason": "rate_limited"})
        return _login_page(request, error=THROTTLED_ERROR, email=email.strip(), status=429)

    result = authenticate(db, email, password)
    if result.user is None:
        throttle.record_failure(ip)
        audit(request, background, "login_failed", user_id=result.user_id,
              detail={"reason": result.reason})  # fmt: skip
        return _login_page(request, error=GENERIC_ERROR, email=email.strip(), status=400)
    throttle.clear(ip)

    # Rotate: any session the browser already had is discarded before issuing a new one.
    old = session_token(request)
    if old:
        sessions.delete_token(db, old)
    token = sessions.create(
        db, result.user, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    audit(request, background, "login", user_id=result.user.id)
    response = RedirectResponse("/patients", status_code=303)
    set_session_cookie(response, token)
    response.delete_cookie(LOGIN_COOKIE, path="/login")
    return response


@router.post("/logout")
def logout(
    request: Request,
    background: BackgroundTasks,
    db: Db,
    csrf_token: Annotated[str, Form(alias=CSRF_FIELD, max_length=200)] = "",
) -> Response:
    token = session_token(request)
    found = sessions.resolve(db, token) if token else None
    if found is not None:
        if not tokens_match(csrf_for_session(token), csrf_token):
            raise HTTPException(status_code=403)
        sessions.delete_token(db, token)
        audit(request, background, "logout", user_id=found[1].id)
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response)
    return response
