import pytest

from app import auth
from app.config import settings


@pytest.fixture()
def password(monkeypatch):
    monkeypatch.setattr(settings, "app_password", "secreta")
    auth._failed_logins.clear()
    return "secreta"


def test_without_password_everything_is_open(client):
    assert client.get("/api/tweets").status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 200
    assert client.get("/api/auth/status").json() == {"enabled": False, "authenticated": True}


def test_with_password_api_requires_session(client, password):
    res = client.get("/api/tweets")
    assert res.status_code == 401


def test_with_password_index_redirects_to_login(client, password):
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"


def test_with_password_public_paths_stay_open(client, password):
    assert client.get("/login").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert client.get("/static/manifest.webmanifest").status_code == 200
    assert client.get("/api/auth/status").json() == {"enabled": True, "authenticated": False}


def test_login_wrong_password_returns_401(client, password):
    res = client.post("/api/auth/login", json={"password": "otra"})
    assert res.status_code == 401
    assert client.get("/api/tweets").status_code == 401


def test_login_then_access_then_logout(client, password):
    res = client.post("/api/auth/login", json={"password": password})
    assert res.status_code == 204
    cookie = res.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie

    assert client.get("/api/tweets").status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 200

    client.post("/api/auth/logout")
    assert client.get("/api/tweets").status_code == 401


def test_session_token_rejects_tampering_and_expiry(password):
    token = auth.make_session_token(now=1_000)
    assert auth.is_valid_session_token(token, now=1_001)

    expires, signature = token.split(".")
    assert not auth.is_valid_session_token(f"{int(expires) + 1}.{signature}", now=1_001)
    assert not auth.is_valid_session_token(token, now=int(expires) + 1)
    assert not auth.is_valid_session_token("basura", now=1_001)
    assert not auth.is_valid_session_token(None, now=1_001)


def test_changing_password_invalidates_sessions(client, password, monkeypatch):
    client.post("/api/auth/login", json={"password": password})
    assert client.get("/api/tweets").status_code == 200

    monkeypatch.setattr(settings, "app_password", "nueva")
    assert client.get("/api/tweets").status_code == 401


def test_assetlinks_is_public_and_404_when_missing(client, password):
    assert client.get("/.well-known/assetlinks.json").status_code == 404
