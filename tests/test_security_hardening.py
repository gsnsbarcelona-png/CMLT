import pytest

from app import auth
from app.config import settings
from app.services.image_urls import is_allowed_image_url
from app.services.x_service import XPublishError, _load_image_bytes

VALID_LOCAL = "/data/images/" + "a" * 32 + ".png"


@pytest.mark.parametrize(
    "url",
    [VALID_LOCAL, "https://static.lolesports.com/teams/x.png", "http://am-a.akamaihd.net/image/x.png"],
)
def test_allowed_image_urls(url):
    assert is_allowed_image_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "../.env",
        "data/tweets.db",
        "/data/images/../../.env",
        "/data/images/abc.png",
        "http://169.254.169.254/latest/meta-data",
        "https://evil.com/lolesports.com/x.png",
        "https://lolesports.com.evil.com/x.png",
        'x" onerror="alert(1)',
    ],
)
def test_rejected_image_urls(url):
    assert not is_allowed_image_url(url)


def test_create_tweet_rejects_bad_image_url_and_source(client):
    assert client.post("/api/tweets", json={"content": "x", "image_url": "../.env"}).status_code == 422
    assert client.post("/api/tweets", json={"content": "x", "source": "<img src=x>"}).status_code == 422
    ok = client.post("/api/tweets", json={"content": "x", "source": "top-ranking", "image_url": VALID_LOCAL})
    assert ok.status_code == 201


def test_update_tweet_rejects_bad_image_url(client):
    tweet = client.post("/api/tweets", json={"content": "x"}).json()
    res = client.put(f"/api/tweets/{tweet['id']}", json={"content": "x", "image_url": "data/tweets.db"})
    assert res.status_code == 422


def test_load_image_bytes_refuses_arbitrary_paths():
    with pytest.raises(XPublishError):
        _load_image_bytes("../.env")


def test_security_headers_present(client):
    res = client.get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "script-src 'self'" in res.headers["Content-Security-Policy"]


def test_login_locks_out_after_repeated_failures(client, monkeypatch):
    monkeypatch.setattr(settings, "app_password", "secreta")
    auth._failed_logins.clear()
    for _ in range(auth.MAX_FAILED_LOGINS):
        assert client.post("/api/auth/login", json={"password": "mal"}).status_code == 401
    locked = client.post("/api/auth/login", json={"password": "secreta"})
    assert locked.status_code == 429
    assert "Retry-After" in locked.headers
    auth._failed_logins.clear()
    assert client.post("/api/auth/login", json={"password": "secreta"}).status_code == 204


def test_app_refuses_to_start_on_render_without_password(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(settings, "app_password", "")
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass
