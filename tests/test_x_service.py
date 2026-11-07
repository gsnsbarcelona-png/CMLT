from types import SimpleNamespace

import pytest
import tweepy

from app.services import x_service


class _FakeHttpResponse:
    def __init__(self, status_code, reason="Error", json_data=None):
        self.status_code = status_code
        self.reason = reason
        self._json = json_data or {}

    def json(self):
        return self._json


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(x_service.settings, "x_api_key", "key")
    monkeypatch.setattr(x_service.settings, "x_api_secret", "secret")
    monkeypatch.setattr(x_service.settings, "x_access_token", "token")
    monkeypatch.setattr(x_service.settings, "x_access_token_secret", "token_secret")


def test_not_configured_raises(monkeypatch):
    monkeypatch.setattr(x_service.settings, "x_api_key", "")
    with pytest.raises(x_service.XNotConfiguredError):
        x_service.publish_tweet("hola")


def test_successful_publish_returns_id(mocker):
    fake_response = SimpleNamespace(data={"id": "12345", "text": "hola"})
    mocker.patch("tweepy.Client.create_tweet", return_value=fake_response)

    result = x_service.publish_tweet("hola")

    assert result == "12345"


def test_unauthorized_translated(mocker):
    error = tweepy.errors.Unauthorized(_FakeHttpResponse(401, "Unauthorized", {"detail": "invalid token"}))
    mocker.patch("tweepy.Client.create_tweet", side_effect=error)

    with pytest.raises(x_service.XPublishError, match="inválidas"):
        x_service.publish_tweet("hola")


def test_forbidden_duplicate_translated(mocker):
    error = tweepy.errors.Forbidden(
        _FakeHttpResponse(403, "Forbidden", {"detail": "You are not allowed to create a Tweet with duplicate content."})
    )
    mocker.patch("tweepy.Client.create_tweet", side_effect=error)

    with pytest.raises(x_service.XPublishError, match="similar"):
        x_service.publish_tweet("hola")


def test_forbidden_permissions_translated(mocker):
    error = tweepy.errors.Forbidden(_FakeHttpResponse(403, "Forbidden", {"detail": "Insufficient permissions"}))
    mocker.patch("tweepy.Client.create_tweet", side_effect=error)

    with pytest.raises(x_service.XPublishError, match="permisos"):
        x_service.publish_tweet("hola")


def test_too_many_requests_translated(mocker):
    error = tweepy.errors.TooManyRequests(_FakeHttpResponse(429, "Too Many Requests", {"detail": "Rate limit exceeded"}))
    mocker.patch("tweepy.Client.create_tweet", side_effect=error)

    with pytest.raises(x_service.XPublishError, match="Límite"):
        x_service.publish_tweet("hola")


def test_server_error_translated(mocker):
    error = tweepy.errors.TwitterServerError(_FakeHttpResponse(500, "Server Error", {"detail": "oops"}))
    mocker.patch("tweepy.Client.create_tweet", side_effect=error)

    with pytest.raises(x_service.XPublishError, match="prueba de nuevo"):
        x_service.publish_tweet("hola")


def test_publish_without_image_passes_no_media_ids(mocker):
    fake_response = SimpleNamespace(data={"id": "1"})
    create_mock = mocker.patch("tweepy.Client.create_tweet", return_value=fake_response)

    x_service.publish_tweet("hola")

    _, kwargs = create_mock.call_args
    assert kwargs["media_ids"] is None


def test_publish_with_external_image_url_uploads_and_attaches(mocker):
    fake_http_response = SimpleNamespace(content=b"fake-png-bytes", raise_for_status=lambda: None)
    mocker.patch("httpx.get", return_value=fake_http_response)
    fake_media = SimpleNamespace(media_id=987)
    upload_mock = mocker.patch("tweepy.API.media_upload", return_value=fake_media)
    fake_response = SimpleNamespace(data={"id": "1"})
    create_mock = mocker.patch("tweepy.Client.create_tweet", return_value=fake_response)

    result = x_service.publish_tweet("hola", "http://static.lolesports.com/teams/logo.png")

    assert result == "1"
    upload_args, upload_kwargs = upload_mock.call_args
    assert upload_kwargs["filename"] == "logo.png"
    assert upload_kwargs["file"].read() == b"fake-png-bytes"
    _, create_kwargs = create_mock.call_args
    assert create_kwargs["media_ids"] == ["987"]


def test_publish_with_local_image_url_reads_from_disk(mocker, tmp_path, monkeypatch):
    monkeypatch.setattr(x_service, "_PROJECT_ROOT", tmp_path)
    images_dir = tmp_path / "data" / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png").write_bytes(b"local-bytes")

    fake_media = SimpleNamespace(media_id=1)
    upload_mock = mocker.patch("tweepy.API.media_upload", return_value=fake_media)
    mocker.patch("tweepy.Client.create_tweet", return_value=SimpleNamespace(data={"id": "1"}))

    x_service.publish_tweet("hola", "/data/images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png")

    _, upload_kwargs = upload_mock.call_args
    assert upload_kwargs["file"].read() == b"local-bytes"


def test_publish_image_download_failure_raises(mocker):
    import httpx

    mocker.patch("httpx.get", side_effect=httpx.ConnectError("boom"))

    with pytest.raises(x_service.XPublishError, match="descargar"):
        x_service.publish_tweet("hola", "http://static.lolesports.com/teams/logo.png")


def test_publish_local_image_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(x_service, "_PROJECT_ROOT", tmp_path)

    with pytest.raises(x_service.XPublishError, match="No se encontró"):
        x_service.publish_tweet("hola", "/data/images/cccccccccccccccccccccccccccccccc.png")


def test_publish_media_upload_rejected_raises(mocker):
    mocker.patch("httpx.get", return_value=SimpleNamespace(content=b"x", raise_for_status=lambda: None))
    mocker.patch("tweepy.API.media_upload", side_effect=tweepy.errors.TweepyException("nope"))

    with pytest.raises(x_service.XPublishError, match="rechazó la imagen"):
        x_service.publish_tweet("hola", "http://static.lolesports.com/teams/logo.png")


def test_publish_with_generated_card_png(mocker, tmp_path, monkeypatch):
    """image_url de una tarjeta generada (PNG en IMAGES_DIR) se sube y se adjunta."""
    monkeypatch.setattr(x_service, "_PROJECT_ROOT", tmp_path)
    images_dir = tmp_path / "data" / "images"
    images_dir.mkdir(parents=True)
    png = b"\x89PNG\r\n\x1a\n" + b"card"
    (images_dir / "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png").write_bytes(png)

    upload_mock = mocker.patch("tweepy.API.media_upload", return_value=SimpleNamespace(media_id=7))
    create_mock = mocker.patch("tweepy.Client.create_tweet", return_value=SimpleNamespace(data={"id": "9"}))

    assert x_service.publish_tweet("hola", "/data/images/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png") == "9"

    assert upload_mock.call_args.kwargs["file"].read() == png
    assert create_mock.call_args.kwargs["media_ids"] == ["7"]
