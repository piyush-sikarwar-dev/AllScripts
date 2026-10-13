"""Phase 2: sign-in, lockout, sessions, CSRF, audit trail, security headers."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.auth.tokens import SESSION_COOKIE
from app.db.app import new_session
from app.repositories.appdb import sessions as session_repo
from app.repositories.appdb import utcnow
from app.repositories.appdb.models import AuditLog, User, UserSession
from tests.conftest import TEST_EMAIL, page_csrf, sign_in
from tests.fakes.data import PATIENTS

FIRST = f"EMR:{PATIENTS[0].emr_id}"
HTMX = {"HX-Request": "true"}


def audit_rows() -> list[AuditLog]:
    with new_session() as db:
        return list(db.scalars(select(AuditLog).order_by(AuditLog.id)))


def get_user() -> User:
    with new_session() as db:
        return db.scalar(select(User).where(User.email == TEST_EMAIL))


# --- protected routes -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/patients", f"/patients/{FIRST}", f"/patients/{FIRST}/tab/labs", "/patients/rows",
     "/release-log"],
)  # fmt: skip
def test_protected_routes_redirect_to_login(anon_client, path):
    r = anon_client.get(path, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_htmx_request_without_session_gets_hx_redirect(anon_client):
    r = anon_client.get(f"/patients/{FIRST}/tab/labs", headers=HTMX, follow_redirects=False)
    assert r.status_code == 204
    assert r.headers["HX-Redirect"] == "/login"


def test_public_routes(anon_client):
    assert anon_client.get("/healthz").status_code == 200
    assert anon_client.get("/login").status_code == 200
    assert anon_client.get("/static/css/app.css").status_code == 200


# --- login ----------------------------------------------------------------------------------


def test_login_success_sets_secure_session_cookie(anon_client, staff_user):
    r = sign_in(anon_client)
    assert r.status_code == 303 and r.headers["location"] == "/patients"
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert anon_client.get("/patients").status_code == 200
    assert get_user().last_login_at is not None
    assert [a.action for a in audit_rows()] == ["login", "search"]


def test_session_token_is_stored_hashed(anon_client, staff_user):
    sign_in(anon_client)
    raw = anon_client.cookies.get(SESSION_COOKIE).rsplit(".", 1)[0]
    with new_session() as db:
        ids = list(db.scalars(select(UserSession.id)))
    assert ids == [session_repo.token_hash(raw)]
    assert raw not in ids


@pytest.mark.parametrize(
    ("email", "password"),
    [(TEST_EMAIL, "wrong password!!"), ("nobody@example.invalid", "whatever password")],
)
def test_login_failure_is_generic(anon_client, staff_user, email, password):
    r = sign_in(anon_client, email, password)
    assert r.status_code == 400
    assert "Email or password is incorrect." in r.text
    assert SESSION_COOKIE not in anon_client.cookies
    rows = audit_rows()
    assert [a.action for a in rows] == ["login_failed"]
    assert email not in str(rows[0].detail)  # no credentials in the audit trail


def test_lockout_after_five_failures(anon_client, staff_user):
    for _ in range(5):
        assert sign_in(anon_client, TEST_EMAIL, "wrong password!!").status_code == 400
    assert get_user().locked_until is not None
    # Even the correct password is refused while locked, with the same generic message.
    r = sign_in(anon_client)
    assert r.status_code == 400 and "Email or password is incorrect." in r.text
    assert audit_rows()[-1].detail == {"reason": "locked"}


def test_lockout_expires(anon_client, staff_user):
    with new_session() as db:
        user = db.scalar(select(User))
        user.locked_until = utcnow() - timedelta(seconds=1)
        db.commit()
    assert sign_in(anon_client).status_code == 303


def test_inactive_user_cannot_sign_in(anon_client, staff_user):
    with new_session() as db:
        db.scalar(select(User)).is_active = False
        db.commit()
    assert sign_in(anon_client).status_code == 400


def test_login_rejects_missing_csrf(anon_client, staff_user):
    anon_client.get("/login")
    r = anon_client.post("/login", data={"email": TEST_EMAIL, "password": "x"})
    assert r.status_code == 403


def test_login_issues_a_new_session_each_time(anon_client, staff_user):
    sign_in(anon_client)
    first = anon_client.cookies.get(SESSION_COOKIE)
    _age_session(last_seen_at=utcnow() - timedelta(minutes=16))  # idle → login form again
    assert sign_in(anon_client).status_code == 303
    assert anon_client.cookies.get(SESSION_COOKIE) != first
    with new_session() as db:
        assert len(list(db.scalars(select(UserSession)))) == 1


def test_signed_in_user_visiting_login_is_redirected(client):
    r = client.get("/login", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/patients"


# --- sessions -------------------------------------------------------------------------------


def _age_session(**changes):
    with new_session() as db:
        s = db.scalar(select(UserSession))
        for key, value in changes.items():
            setattr(s, key, value)
        db.commit()


def test_idle_timeout(client):
    _age_session(last_seen_at=utcnow() - timedelta(minutes=16))
    r = client.get("/patients", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    with new_session() as db:
        assert db.scalar(select(UserSession)) is None  # expired session deleted


def test_absolute_timeout(client):
    _age_session(expires_at=utcnow() - timedelta(seconds=1))
    assert client.get("/patients", follow_redirects=False).status_code == 303


def test_activity_keeps_session_alive(client):
    _age_session(last_seen_at=utcnow() - timedelta(minutes=10))
    assert client.get("/patients").status_code == 200
    with new_session() as db:
        last_seen = db.scalar(select(UserSession.last_seen_at))
    assert last_seen.replace(tzinfo=None) > (utcnow() - timedelta(minutes=1)).replace(tzinfo=None)


def test_tampered_cookie_is_rejected(client):
    value = client.cookies.get(SESSION_COOKIE)
    client.cookies.set(SESSION_COOKIE, value[:-2] + "xx")
    assert client.get("/patients", follow_redirects=False).status_code == 303


def test_deactivated_user_loses_session(client):
    with new_session() as db:
        db.scalar(select(User)).is_active = False
        db.commit()
    assert client.get("/patients", follow_redirects=False).status_code == 303


# --- logout / CSRF --------------------------------------------------------------------------


def test_logout_requires_csrf(client):
    r = client.post("/logout", data={"csrf_token": "forged"}, follow_redirects=False)
    assert r.status_code == 403
    assert client.get("/patients", follow_redirects=False).status_code == 200


def test_logout_deletes_session(client):
    token = page_csrf(client)
    r = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/patients", follow_redirects=False).status_code == 303
    with new_session() as db:
        assert db.scalar(select(UserSession)) is None
    assert "logout" in [a.action for a in audit_rows()]


def test_htmx_csrf_header_is_rendered(client):
    html = client.get("/patients").text
    assert 'hx-headers=\'{"X-CSRF-Token": "' in html


def test_require_csrf_dependency():
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.auth import require_csrf

    app = FastAPI()

    @app.post("/x", dependencies=[Depends(require_csrf)])
    def x() -> dict:
        return {}

    assert TestClient(app).post("/x", headers={"X-CSRF-Token": "nope"}).status_code == 403


# --- audit trail ----------------------------------------------------------------------------


def test_chart_views_are_audited(client):
    client.get(f"/patients/{FIRST}?tab=labs")
    client.get(f"/patients/{FIRST}/tab/meds", headers=HTMX)
    visit = PATIENTS[0].visits[0]["encounter_id"]
    client.get(f"/patients/{FIRST}/visits/{visit}", headers=HTMX)
    rows = [a for a in audit_rows() if a.patient_key == FIRST]
    assert [(a.action, a.detail.get("tab")) for a in rows] == [
        ("view_patient", "labs"),
        ("view_tab", "meds"),
        ("view_visit", None),
    ]
    assert rows[-1].detail == {"encounter_id": visit, "view": "structured"}
    user_id = get_user().id
    assert all(a.user_id == user_id and a.request_id and a.ip for a in rows)


def test_search_audit_stores_fields_not_values(client):
    client.get("/patients/rows", params={"q": "Sample, Patient", "dob": "01/02/1960"},
               headers=HTMX)  # fmt: skip
    row = audit_rows()[-1]
    assert row.action == "search"
    assert row.detail == {"fields": ["name", "dob"], "page": 1}
    assert "Sample" not in str(row.detail) and "1960" not in str(row.detail)


def test_audit_failure_is_logged_not_raised(caplog, monkeypatch):
    from app import audit as audit_module

    def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(audit_module.audit_repo, "insert", boom)
    audit_module.write_audit(action="search", user_id=None, patient_key=None, detail={},
                             ip=None, request_id="req-1")  # fmt: skip
    assert "audit write failed action=search request_id=req-1" in caplog.text


def test_unknown_audit_action_rejected():
    from app.repositories.appdb import audit as audit_repo

    with new_session() as db, pytest.raises(ValueError):
        audit_repo.insert(db, action="edit_chart", user_id=None, patient_key=None, detail={},
                          ip=None, request_id=None)  # fmt: skip


# --- security headers -----------------------------------------------------------------------


def test_security_headers(client):
    r = client.get(f"/patients/{FIRST}")
    assert r.headers["Content-Security-Policy"].startswith("default-src 'self'")
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Cache-Control"] == "no-store"
    assert len(r.headers["X-Request-ID"]) >= 8


def test_static_assets_are_cacheable(anon_client):
    r = anon_client.get("/static/css/app.css")
    assert "no-store" not in r.headers.get("Cache-Control", "")


# --- passwords / CLI ------------------------------------------------------------------------


def test_password_rules():
    from app.auth.passwords import hash_password, password_problem, verify_password

    assert password_problem("short") is not None
    assert password_problem(" twelve chars long ") is not None
    assert password_problem("twelve chars ok") is None
    h = hash_password("twelve chars ok")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "twelve chars ok") and not verify_password(h, "nope")


def test_cli_user_lifecycle(monkeypatch, capsys):
    import cli

    answers = iter(["a long enough password", "a long enough password"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(answers))
    assert cli.main(["create-user", "--email", "New@Example.invalid", "--name", "New Person"]) == 0
    with new_session() as db:
        user = db.scalar(select(User).where(User.email == "new@example.invalid"))
    assert user is not None and user.full_name == "New Person"
    assert cli.main(["create-user", "--email", "new@example.invalid", "--name", "Dup"]) == 1
    assert cli.main(["deactivate-user", "--email", "new@example.invalid"]) == 0
    with new_session() as db:
        assert db.get(User, user.id).is_active is False


def test_cli_rejects_short_password(monkeypatch, capsys):
    import cli

    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "short")
    assert cli.main(["create-user", "--email", "x@example.invalid", "--name", "X"]) == 1
    assert "at least 12 characters" in capsys.readouterr().out


# --- perf #7: tabs re-shown from page memory are still audited -----------------------------------


def test_tab_seen_records_audit_row(client):
    token = page_csrf(client)
    r = client.post(f"/patients/{FIRST}/tab/labs/seen", headers={"X-CSRF-Token": token})
    assert r.status_code == 204 and r.content == b""
    row = audit_rows()[-1]
    assert (row.action, row.patient_key) == ("view_tab", FIRST)
    assert row.detail == {"tab": "labs", "from_page_memory": True}


def test_tab_seen_requires_csrf_session_and_valid_tab(client, anon_client):
    assert client.post(f"/patients/{FIRST}/tab/labs/seen").status_code == 403
    token = page_csrf(client)
    bad = client.post(f"/patients/{FIRST}/tab/secrets/seen", headers={"X-CSRF-Token": token})
    assert bad.status_code == 404
    other = client.post("/patients/EMR:999999/tab/labs/seen", headers={"X-CSRF-Token": token})
    assert other.status_code == 404
