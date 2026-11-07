import base64

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _hdr(pw):
    return {"Authorization": "Basic " + base64.b64encode(f"u:{pw}".encode()).decode()}


def test_auth_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "app_password", "")
    assert TestClient(app).get("/api/config/check").status_code == 200


def test_auth_enforced(monkeypatch):
    monkeypatch.setattr(settings, "app_password", "s3cret")
    c = TestClient(app)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/config/check").status_code == 401
    assert c.get("/api/config/check", headers=_hdr("bad")).status_code == 401
    assert c.get("/api/config/check", headers=_hdr("s3cret")).status_code == 200
