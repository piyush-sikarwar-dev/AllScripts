"""Production safety checks and the sign-in throttle (docs/SECURITY.md).

- `production_problems()`: settings that must be right before the app may serve real data. In
  APP_ENV=production the app refuses to start while any are wrong (fail closed).
- `sql_login_problems()`: the archive login must not be able to write. Checked with read-only
  catalog functions (meta/login_permissions.sql) at start-up and by /readyz.
- `LoginThrottle`: per-IP limit on failed sign-ins, on top of the per-account lockout (5 failures
  lock the account for 15 minutes). Kept in memory per process; the WAF rate rule covers the
  whole fleet.
"""

import logging
import threading
import time
from collections import deque

from app.config import Settings, get_settings
from app.db.source import Source, configured_sources
from app.repositories.base import run_query

log = logging.getLogger("app.security")

MIN_SECRET_LENGTH = 32
_WRITE_PERMISSIONS = ("is_sysadmin", "is_db_owner", "is_datawriter", "can_insert", "can_update",
                      "can_delete", "can_alter")  # fmt: skip


def is_production(settings: Settings | None = None) -> bool:
    return (settings or get_settings()).app_env.strip().lower() == "production"


def production_problems(settings: Settings | None = None) -> list[str]:
    """What is wrong for production, by setting name. Never includes setting values."""
    s = settings or get_settings()
    problems = []
    if len(s.session_secret.get_secret_value()) < MIN_SECRET_LENGTH:
        problems.append(f"SESSION_SECRET must be set (at least {MIN_SECRET_LENGTH} characters)")
    if not s.cookie_secure:
        problems.append("COOKIE_SECURE must be true")
    if s.use_fake_data:
        problems.append("USE_FAKE_DATA must be false")
    if not s.allowed_hosts.strip():
        problems.append("ALLOWED_HOSTS must list the site's host name(s)")
    if "sslmode=require" not in s.app_database_url and "sslmode=verify" not in s.app_database_url:
        problems.append("APP_DATABASE_URL must use sslmode=require (or verify-full)")
    return problems


def sql_login_problems() -> dict[str, str]:
    """{database: problem} for every configured source the login could write to, or could not be
    checked. Empty when the login is read-only everywhere."""
    problems: dict[str, str] = {}
    for source in configured_sources():
        try:
            perms = run_query(source, "meta/login_permissions.sql")[0]
        except Exception:
            problems[source.value] = "permission check failed"
            continue
        granted = [p for p in _WRITE_PERMISSIONS if perms.get(p)]
        if granted:
            problems[source.value] = "login can write (" + ", ".join(granted) + ")"
    return problems


def check_production_start() -> None:
    """Raise RuntimeError (start-up fails) when production settings or the SQL login are unsafe."""
    settings = get_settings()
    if not is_production(settings):
        return
    if settings.sql_trust_server_certificate:  # still encrypted, but the server is not verified
        log.warning("SQL_TRUST_SERVER_CERTIFICATE=true: the SQL Server certificate is not verified")
    problems = production_problems(settings)
    if problems:
        raise RuntimeError("unsafe production configuration: " + "; ".join(problems))
    sql = sql_login_problems()
    if sql and not settings.allow_writable_sql_login:
        detail = "; ".join(f"{db}: {p}" for db, p in sql.items())
        raise RuntimeError(
            "the archive SQL login must be read-only (docs/DEPLOYMENT_PLAN.md §4): " + detail
        )


class LoginThrottle:
    """Sliding window of failed sign-ins per client IP."""

    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, ip: str, now: float) -> deque[float]:
        q = self._failures.setdefault(ip, deque())
        while q and q[0] <= now - self.window:
            q.popleft()
        return q

    def blocked(self, ip: str | None) -> bool:
        if not ip:
            return False
        with self._lock:
            return len(self._recent(ip, time.monotonic())) >= self.max_failures

    def record_failure(self, ip: str | None) -> None:
        if not ip:
            return
        with self._lock:
            self._recent(ip, time.monotonic()).append(time.monotonic())
            if len(self._failures) > 10_000:  # bound memory under a spray from many addresses
                for key in list(self._failures)[:5_000]:
                    del self._failures[key]

    def clear(self, ip: str | None) -> None:
        if ip:
            with self._lock:
                self._failures.pop(ip, None)


_throttle: LoginThrottle | None = None


def login_throttle() -> LoginThrottle:
    global _throttle
    if _throttle is None:
        s = get_settings()
        _throttle = LoginThrottle(s.login_ip_max_failures, s.login_ip_window_minutes * 60)
    return _throttle


__all__ = ["Source", "check_production_start", "login_throttle", "production_problems",
           "sql_login_problems"]  # fmt: skip
