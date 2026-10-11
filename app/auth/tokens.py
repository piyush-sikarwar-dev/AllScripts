"""HMAC signing for the session cookie and CSRF tokens (keyed by SESSION_SECRET)."""

import base64
import hashlib
import hmac
import logging
import secrets
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger("app.auth")

SESSION_COOKIE = "lv_session"
LOGIN_COOKIE = "lv_login"  # pre-login nonce for the sign-in form's CSRF token


@lru_cache
def _secret() -> bytes:
    secret = get_settings().session_secret.get_secret_value()
    if not secret:
        log.warning("SESSION_SECRET is not set; using a random key (sessions end on restart)")
        return secrets.token_bytes(32)
    return secret.encode("utf-8")


def _mac(purpose: str, value: str) -> str:
    digest = hmac.new(_secret(), f"{purpose}:{value}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def sign_session(token: str) -> str:
    return f"{token}.{_mac('session', token)}"


def unsign_session(cookie: str | None) -> str | None:
    """Raw session token from a signed cookie value, or None if missing / tampered."""
    if not cookie or "." not in cookie:
        return None
    token, _, sig = cookie.rpartition(".")
    if not token or not hmac.compare_digest(sig, _mac("session", token)):
        return None
    return token


def csrf_for_session(token: str) -> str:
    return _mac("csrf", token)


def new_login_nonce() -> str:
    return secrets.token_urlsafe(24)


def csrf_for_login(nonce: str) -> str:
    return _mac("login-csrf", nonce)


def tokens_match(expected: str, supplied: str | None) -> bool:
    return bool(supplied) and hmac.compare_digest(expected, supplied or "")
