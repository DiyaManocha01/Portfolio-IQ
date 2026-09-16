import pytest
from fastapi.testclient import TestClient

from app.data.seed import DEMO_EMAIL, DEMO_PASSWORD
from app.main import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def auth_token(client):
    """Logs in as the seeded demo user. Assumes `python -m app.data.seed` has been run."""
    resp = client.post("/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, "Demo user not found -- run `python -m app.data.seed` before tests"
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}
