import uuid


def test_register_login_and_me(client):
    email = f"pytest-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/auth/register", json={"email": email, "password": "testpass123", "full_name": "Pytest User"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == email
    token = body["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    login = client.post("/auth/login", json={"email": email, "password": "testpass123"})
    assert login.status_code == 200


def test_register_duplicate_email_rejected(client):
    email = f"pytest-dup-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/auth/register", json={"email": email, "password": "testpass123", "full_name": "A"})
    resp = client.post("/auth/register", json={"email": email, "password": "testpass123", "full_name": "B"})
    assert resp.status_code == 400


def test_login_wrong_password_rejected(client, auth_headers):
    resp = client.post("/auth/login", json={"email": "demo@portfolioiq.app", "password": "wrong-password"})
    assert resp.status_code == 401


def test_protected_route_requires_token(client):
    resp = client.get("/portfolio")
    assert resp.status_code == 401
