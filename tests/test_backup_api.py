def test_backup_roundtrip_and_no_duplicates(client):
    client.post("/api/tweets", json={"content": "uno", "source": "h2h"})
    client.post("/api/tweets", json={"content": "dos"})

    backup = client.get("/api/backup").json()
    assert backup["version"] == 1
    assert [t["content"] for t in backup["tweets"]] == ["uno", "dos"]

    # Restaurar sobre los mismos datos no duplica nada.
    assert client.post("/api/restore", json=backup).json() == {"tweets_added": 0}

    # Borramos todo y restauramos.
    for t in client.get("/api/tweets").json():
        client.delete(f"/api/tweets/{t['id']}")
    assert client.get("/api/tweets").json() == []
    assert client.post("/api/restore", json=backup).json() == {"tweets_added": 2}
    assert len(client.get("/api/tweets").json()) == 2


def test_restore_drops_invalid_image_urls(client):
    backup = {"tweets": [{"content": "con imagen mala", "image_url": "../.env"}]}
    assert client.post("/api/restore", json=backup).json()["tweets_added"] == 1
    assert client.get("/api/tweets").json()[0]["image_url"] is None


def test_restore_accepts_old_backup_with_templates_key(client):
    old = {"version": 1, "tweets": [{"content": "viejo"}], "templates": [{"name": "x", "template_text": "y"}]}
    assert client.post("/api/restore", json=old).json() == {"tweets_added": 1}


def test_database_url_normalization():
    from app.db import _normalize_database_url

    assert _normalize_database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert (
        _normalize_database_url("postgresql://u:p@h/db?sslmode=require")
        == "postgresql+psycopg://u:p@h/db?sslmode=require"
    )
    assert _normalize_database_url("sqlite:///./data/tweets.db") == "sqlite:///./data/tweets.db"


def test_health_checks_database(client):
    assert client.get("/api/health").json() == {"status": "ok"}
