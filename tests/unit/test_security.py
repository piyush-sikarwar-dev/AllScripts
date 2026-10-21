"""Security controls (docs/SECURITY.md): headers, host check, sign-in throttle, request log without
PHI, fail-closed production start-up, read-only SQL login check, CSRF and access control."""

import logging

import pytest
from pydantic import SecretStr

from app.config import get_settings
from app.security import LoginThrottle, production_problems
from tests.conftest import TEST_EMAIL, login_csrf
from tests.fakes.data import PATIENTS


def test_security_headers_on_every_page(client):
    r = client.get("/patients")
    h = r.headers
    for part in ("default-src 'self'", "script-src 'self'", "frame-ancestors 'none'",
                 "base-uri 'none'", "form-action 'self'", "object-src 'none'"):  # fmt: skip
        assert part in h["Content-Security-Policy"], part
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer" and h["Cache-Control"] == "no-store"
    assert "camera=()" in h["Permissions-Policy"]
    assert h["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "Strict-Transport-Security" not in h  # COOKIE_SECURE=false in tests (plain http)


def test_hsts_when_cookies_are_secure(client, monkeypatch):
    import app.middleware as mw

    secure = get_settings().model_copy(update={"cookie_secure": True})
    monkeypatch.setattr(mw, "get_settings", lambda: secure)
    assert "max-age=31536000" in client.get("/patients").headers["Strict-Transport-Security"]


def test_unknown_host_is_rejected(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    hosts = get_settings().model_copy(update={"allowed_hosts": "records.example.org"})
    monkeypatch.setattr(main, "get_settings", lambda: hosts)
    with TestClient(main.create_app(), base_url="http://evil.example.com") as c:
        assert c.get("/login").status_code == 400
    with TestClient(main.create_app(), base_url="http://records.example.org") as c:
        assert c.get("/healthz").status_code == 200
    with TestClient(main.create_app(), base_url="http://10.0.1.23:8000") as c:  # ALB probe by IP
        assert c.get("/healthz").status_code == 200
        assert c.get("/patients", follow_redirects=False).status_code == 400


def test_login_throttle_per_ip(anon_client, staff_user, monkeypatch):
    import app.security as security

    monkeypatch.setattr(security, "_throttle", LoginThrottle(max_failures=3, window_seconds=900))
    for _ in range(3):
        r = anon_client.post("/login", data={"email": TEST_EMAIL, "password": "wrong password!!",
                                              "csrf_token": login_csrf(anon_client)})  # fmt: skip
        assert r.status_code == 400
    r = anon_client.post("/login", data={"email": TEST_EMAIL, "password": "correct horse battery",
                                          "csrf_token": login_csrf(anon_client)})  # fmt: skip
    assert r.status_code == 429 and "Too many sign-in attempts" in r.text  # even the right one


def test_throttle_window_and_clear():
    t = LoginThrottle(max_failures=2, window_seconds=900)
    t.record_failure("10.0.0.1")
    assert not t.blocked("10.0.0.1")
    t.record_failure("10.0.0.1")
    assert t.blocked("10.0.0.1") and not t.blocked("10.0.0.2")
    t.clear("10.0.0.1")
    assert not t.blocked("10.0.0.1")
    t.window = 0  # everything is outside the window
    t.record_failure("10.0.0.3")
    assert not t.blocked("10.0.0.3")


def test_request_log_has_no_phi(client, caplog):
    p = PATIENTS[0]
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/patients/rows", params={"q": p.last_name}, headers={"HX-Request": "true"})
        client.get(f"/patients/EMR:{p.emr_id}")
    lines = [r.getMessage() for r in caplog.records if r.name == "app.request"]
    assert any("route=/patients/rows" in m and "status=200" in m for m in lines)
    assert any("route=/patients/{key}" in m for m in lines)
    joined = "\n".join(lines)
    assert p.last_name not in joined and str(p.emr_id) not in joined and "q=" not in joined


def test_production_problems_lists_unsafe_settings():
    base = get_settings().model_copy(update={
        "app_env": "production", "session_secret": SecretStr("short"), "cookie_secure": False,
        "use_fake_data": True, "allowed_hosts": "",
        "app_database_url": "postgresql+psycopg://x/y"})  # fmt: skip
    problems = " | ".join(production_problems(base))
    for name in ("SESSION_SECRET", "COOKIE_SECURE", "USE_FAKE_DATA", "ALLOWED_HOSTS",
                 "APP_DATABASE_URL"):  # fmt: skip
        assert name in problems
    assert "short" not in problems  # never echoes a secret
    good = base.model_copy(update={
        "session_secret": SecretStr("x" * 48), "cookie_secure": True, "use_fake_data": False,
        "allowed_hosts": "records.example.org",
        "app_database_url": "postgresql+psycopg://x/y?sslmode=require"})  # fmt: skip
    assert production_problems(good) == []


def test_production_refuses_to_start_when_unsafe(monkeypatch):
    import app.security as security

    bad = get_settings().model_copy(update={"app_env": "production"})
    monkeypatch.setattr(security, "get_settings", lambda: bad)
    with pytest.raises(RuntimeError, match="unsafe production configuration"):
        security.check_production_start()


def test_production_refuses_writable_sql_login(monkeypatch):
    import app.security as security

    ok = get_settings().model_copy(update={
        "app_env": "production", "session_secret": SecretStr("x" * 48), "cookie_secure": True,
        "use_fake_data": False, "allowed_hosts": "records.example.org",
        "app_database_url": "postgresql+psycopg://x/y?sslmode=require"})  # fmt: skip
    monkeypatch.setattr(security, "get_settings", lambda: ok)
    monkeypatch.setattr(security, "configured_sources", lambda: [security.Source.EMR])
    monkeypatch.setattr(security, "run_query", lambda *a, **k: [{"is_datawriter": 1}])
    with pytest.raises(RuntimeError, match="must be read-only"):
        security.check_production_start()
    monkeypatch.setattr(security, "run_query", lambda *a, **k: [{"is_datareader": 1}])
    security.check_production_start()  # read-only login: starts


def test_every_post_requires_csrf(client):
    p = PATIENTS[0]
    key = f"EMR:{p.emr_id}"
    for path in (f"/patients/{key}/export", f"/patients/{key}/tab/overview/seen"):
        assert client.post(path, data={}).status_code == 403
    assert client.post("/logout", data={"csrf_token": "forged"}).status_code == 403


def test_signed_out_users_see_nothing(anon_client):
    p = PATIENTS[0]
    for path in ("/patients", f"/patients/EMR:{p.emr_id}", f"/patients/EMR:{p.emr_id}/photo",
                 "/release-log", "/legacy"):  # fmt: skip
        r = anon_client.get(path, follow_redirects=False)
        assert r.status_code in (303, 307) and r.headers["location"].endswith("/login"), path


def test_tampered_session_cookie_is_ignored(client):
    from app.auth.tokens import SESSION_COOKIE

    value = client.cookies.get(SESSION_COOKIE)
    client.cookies.set(SESSION_COOKIE, value[:-2] + ("AA" if not value.endswith("AA") else "BB"))
    r = client.get("/patients", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/login")
