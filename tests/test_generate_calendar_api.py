from datetime import datetime, timezone

from app.services.ai_service import AIGenerationError
from app.services.lolesports_service import LoLEsportsError, MatchInfo


def _match(league_slug="les"):
    return MatchInfo(
        start_time=datetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc),
        state="unstarted",
        league_slug=league_slug,
        block_name="Grupos",
        team1_name="Movistar KOI Fenix",
        team1_code="MKF",
        team2_name="UCAM Esports Club",
        team2_code="UCAM",
    )


def test_generate_calendar_success(client, mocker):
    mocker.patch("app.routers.generate.calendar.fetch_upcoming_matches", return_value=[_match()])

    res = client.post("/api/generate/calendar", json={"leagues": ["les"]})

    assert res.status_code == 200
    body = res.json()
    assert "MKF 🆚 UCAM" in body["content"]
    assert body["char_count"] > 0


def test_generate_calendar_requires_league(client):
    res = client.post("/api/generate/calendar", json={"leagues": []})
    assert res.status_code == 400


def test_generate_calendar_rejects_unknown_league(client):
    res = client.post("/api/generate/calendar", json={"leagues": ["lck"]})
    assert res.status_code == 400


def test_generate_calendar_service_error_returns_502(client, mocker):
    mocker.patch(
        "app.routers.generate.calendar.fetch_upcoming_matches",
        side_effect=LoLEsportsError("no se pudo obtener el calendario"),
    )

    res = client.post("/api/generate/calendar", json={"leagues": ["les", "lec"]})

    assert res.status_code == 502
    assert "calendario" in res.json()["detail"]


def test_generate_calendar_hype_style_uses_ai(client, mocker):
    mocker.patch("app.routers.generate.calendar.fetch_upcoming_matches", return_value=[_match()])
    hype_mock = mocker.patch(
        "app.routers.generate.calendar.generate_hype_calendar", return_value="Semana decisiva en la LES!"
    )

    res = client.post("/api/generate/calendar", json={"leagues": ["les"], "style": "hype"})

    assert res.status_code == 200
    assert res.json()["content"].startswith("Semana decisiva en la LES!")
    hype_mock.assert_called_once()
    context_arg, label_arg = hype_mock.call_args.args
    assert "MKF 🆚 UCAM" in context_arg
    assert label_arg == "LES"


def test_generate_calendar_hype_style_ai_failure_returns_502(client, mocker):
    mocker.patch("app.routers.generate.calendar.fetch_upcoming_matches", return_value=[_match()])
    mocker.patch(
        "app.routers.generate.calendar.generate_hype_calendar",
        side_effect=AIGenerationError("Falta configurar ANTHROPIC_API_KEY"),
    )

    res = client.post("/api/generate/calendar", json={"leagues": ["les"], "style": "hype"})

    assert res.status_code == 502
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]


def test_generate_calendar_rejects_unknown_style(client):
    res = client.post("/api/generate/calendar", json={"leagues": ["les"], "style": "flashy"})

    assert res.status_code == 400


def test_generate_calendar_appends_closing_tags(client, mocker):
    mocker.patch("app.routers.generate.calendar.fetch_upcoming_matches", return_value=[_match()])

    res = client.post("/api/generate/calendar", json={"leagues": ["les"]})

    content = res.json()["content"]
    assert "@LESESPORTS" in content
    assert "#LES" in content
    assert "#LT" in content


def test_generate_calendar_accepts_emea_masters_league(client, mocker):
    mocker.patch(
        "app.routers.generate.calendar.fetch_upcoming_matches", return_value=[_match("emea_masters")]
    )

    res = client.post("/api/generate/calendar", json={"leagues": ["emea_masters"]})

    assert res.status_code == 200
    content = res.json()["content"]
    assert "@EMEAmasters" in content
    assert "#EMEAMasters" in content
