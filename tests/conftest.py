import os

import pytest

# Unit tests always run against the in-memory fakes, regardless of a local .env.
os.environ["USE_FAKE_DATA"] = "true"
os.environ.setdefault("SCAN_ROOT", "")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
