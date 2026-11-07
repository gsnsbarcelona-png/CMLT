from datetime import datetime, timezone

from app.db import get_session
from app.main import app
from app.models import Tweet
from app.services import lolesports_service as lol
from app.services.history_service import Anniversary

NOW = datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)  # 11:00 Madrid


class _FakeDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def _match(day_offset, t1="Vodafone Giants", t2="Movistar KOI", hour=18):
    start = datetime(2026, 11, 7 + day_offset, hour, 0, tzinfo=lol.MADRID_TZ)
    return lol.MatchInfo(start, "unstarted", "les", "Semana 1", t1, t1[:3], t2, t2[:3])


def _result(day_offset, hour=18):
    start = datetime(2026, 11, 7 + day_offset, hour, 0, tzinfo=lol.MADRID_TZ)
    return lol.ResultInfo(start, "les", "Semana 1", "A", "A", "B", "B", 2, 1)


def _patch(mocker, upcoming=(), results=()):
    mocker.patch("app.routers.suggestions.datetime", _FakeDatetime)
    mocker.patch.object(lol, "fetch_upcoming_matches", return_value=list(upcoming))
    mocker.patch.object(lol, "fetch_latest_results", return_value=list(results))


def _kinds(client):
    return [s["kind"] for s in client.get("/api/suggestions/today").json()["suggestions"]]


def test_today_match_gives_h2h_and_match_day(client, mocker):
    _patch(mocker, upcoming=[_match(0)])
    body = client.get("/api/suggestions/today").json()
    assert [s["kind"] for s in body["suggestions"]] == ["h2h", "match-day"]
    assert body["suggestions"][0]["params"] == {"team_a": "Vodafone Giants", "team_b": "Movistar KOI"}
    assert body["suggestions"][0]["mode"] == "h2h"


def test_yesterday_results_and_max_four(client, mocker):
    _patch(
        mocker,
        upcoming=[_match(0), _match(0, "X Team", "Y Team", 20), _match(0, "P", "Q", 21), _match(1)],
        results=[_result(-1), _result(-1, 20)],
    )
    s = client.get("/api/suggestions/today").json()["suggestions"]
    assert [x["kind"] for x in s] == ["h2h", "h2h", "match-day", "results"]
    assert s[3]["title"] == "Ayer hubo 2 partidos"


def test_tomorrow_calendar(client, mocker):
    _patch(mocker, upcoming=[_match(1)])
    assert _kinds(client) == ["calendar"]


def test_results_skipped_if_already_tweeted(client, mocker):
    _patch(mocker, results=[_result(-1)], upcoming=[_match(1)])
    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    session.add(Tweet(content="x", source="results", created_at=datetime(2026, 11, 7, 8, 0, tzinfo=timezone.utc)))
    session.commit()
    assert _kinds(client) == ["calendar"]


def test_results_outside_window_ignored(client, mocker):
    _patch(mocker, results=[_result(-3)])
    assert "results" not in _kinds(client)


def test_empty_falls_back_to_anniversary_then_empty_state(client, mocker):
    _patch(mocker)
    anniv = Anniversary(11, 7, 2020, "Hito", "d", "Era", [], None, "s")
    mocker.patch("app.routers.suggestions.find_for_date", return_value=anniv)
    assert _kinds(client) == ["anniversary"]
    mocker.patch("app.routers.suggestions.find_for_date", return_value=None)
    assert _kinds(client) == ["empty"]


def test_api_failure_returns_200_with_error(client, mocker):
    mocker.patch.object(lol, "fetch_upcoming_matches", side_effect=lol.LoLEsportsError("caída"))
    res = client.get("/api/suggestions/today")
    assert res.status_code == 200
    body = res.json()
    assert body["suggestions"] == [] and body["error"]
