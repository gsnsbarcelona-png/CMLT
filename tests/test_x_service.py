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

    with pytest.raises(x_service.XPublishError, match="invalidas"):
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

    with pytest.raises(x_service.XPublishError, match="Limite"):
        x_service.publish_tweet("hola")


def test_server_error_translated(mocker):
    error = tweepy.errors.TwitterServerError(_FakeHttpResponse(500, "Server Error", {"detail": "oops"}))
    mocker.patch("tweepy.Client.create_tweet", side_effect=error)

    with pytest.raises(x_service.XPublishError, match="proba de nuevo"):
        x_service.publish_tweet("hola")
