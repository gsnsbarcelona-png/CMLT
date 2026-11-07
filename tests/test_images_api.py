import io

from app.routers import images as images_module


def _saved_files(images_dir):
    return list(images_dir.iterdir()) if images_dir.exists() else []


def test_upload_image_success(client, tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    monkeypatch.setattr(images_module, "IMAGES_DIR", images_dir)

    res = client.post(
        "/api/images", files={"file": ("logo.png", io.BytesIO(b"fake-png-bytes"), "image/png")}
    )

    assert res.status_code == 200
    body = res.json()
    assert body["image_url"].startswith("/data/images/")
    assert body["image_url"].endswith(".png")
    saved = _saved_files(images_dir)
    assert len(saved) == 1
    assert saved[0].read_bytes() == b"fake-png-bytes"


def test_upload_image_rejects_unsupported_content_type(client, tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    monkeypatch.setattr(images_module, "IMAGES_DIR", images_dir)

    res = client.post(
        "/api/images", files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    )

    assert res.status_code == 400
    assert _saved_files(images_dir) == []


def test_upload_image_rejects_empty_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(images_module, "IMAGES_DIR", tmp_path / "images")

    res = client.post("/api/images", files={"file": ("logo.png", io.BytesIO(b""), "image/png")})

    assert res.status_code == 400


def test_upload_image_rejects_over_size_limit(client, tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    monkeypatch.setattr(images_module, "IMAGES_DIR", images_dir)
    too_big = b"x" * (images_module.MAX_IMAGE_BYTES + 1)

    res = client.post("/api/images", files={"file": ("logo.png", io.BytesIO(too_big), "image/png")})

    assert res.status_code == 400
    assert "5 MB" in res.json()["detail"]
    assert _saved_files(images_dir) == []


def test_upload_image_accepts_jpeg_and_webp(client, tmp_path, monkeypatch):
    monkeypatch.setattr(images_module, "IMAGES_DIR", tmp_path / "images")

    for content_type, ext in (("image/jpeg", ".jpg"), ("image/webp", ".webp")):
        res = client.post("/api/images", files={"file": ("x", io.BytesIO(b"bytes"), content_type)})
        assert res.status_code == 200
        assert res.json()["image_url"].endswith(ext)
