import os
import re

import pytest

# Unit tests always run against the in-memory fakes and an in-memory SQLite app database, and
# never touch a real database, whatever a local .env contains (env vars override .env).
os.environ["USE_FAKE_DATA"] = "true"
os.environ["SCAN_ROOT"] = ""
os.environ["APP_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SESSION_SECRET"] = "unit-test-secret-not-for-production"
os.environ["COOKIE_SECURE"] = "false"  # TestClient talks plain http
if os.environ.get("RUN_INTEGRATION") != "1":
    os.environ["SQL_HOST"] = ""

TEST_EMAIL = "staff@example.invalid"
TEST_PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def app_db():
    """Fresh app-database tables for every test."""
    import app.repositories.appdb.models  # noqa: F401
    from app.db.app import Base, get_app_engine

    engine = get_app_engine()
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def staff_user(app_db):
    from app.auth.passwords import hash_password
    from app.db.app import new_session
    from app.repositories.appdb import users

    with new_session() as db:
        return users.create(
            db,
            email=TEST_EMAIL,
            full_name="Staff Member",
            password_hash=hash_password(TEST_PASSWORD),
        )


def login_csrf(client) -> str:
    html = client.get("/login").text
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def sign_in(client, email: str = TEST_EMAIL, password: str = TEST_PASSWORD):
    return client.post(
        "/login",
        data={"email": email, "password": password, "csrf_token": login_csrf(client)},
        follow_redirects=False,
    )


@pytest.fixture
def anon_client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def client(anon_client, staff_user):
    """A client signed in as the staff user."""
    r = sign_in(anon_client)
    assert r.status_code == 303, r.text
    return anon_client


def page_csrf(client, path: str = "/patients") -> str:
    html = client.get(path).text
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
