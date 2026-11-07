from datetime import datetime, timezone

from app.services.golgg_service import GolGGError, PlayerStat
from app.services.lolesports_service import LoLEsportsError, MatchInfo, RosterPlayer, TeamRosterNotFoundError


def _player(name="Escik", games=15, kda=9.4):
    return PlayerStat(name=name, games=games, win_rate=86.7, kda=kda, csm=9.2, avg_kills=6.7, penta_kills=0, solo_kills=8)


def _roster_a():
    return [RosterPlayer(name="Escik", role="mid")]


def _roster_b():
    return [RosterPlayer(name="Fulano", role="mid")]


def _mock_success(mocker, roster_a=None, roster_b=None, player_stats=None):
    mocker.patch(
        "app.routers.generate.duel.fetch_les_team_roster_with_roles",
        side_effect=lambda name: (roster_a or _roster_a()) if "UCAM" in name else (roster_b or _roster_b()),
    )
    mocker.patch(
        "app.routers.generate.duel.fetch_player_stats",
        return_value=player_stats if player_stats is not None else [_player("Escik"), _player("Fulano", kda=4.0)],
    )


def test_generate_duel_success(client, mocker):
    _mock_success(mocker)

    res = client.post(
        "/api/generate/duel", json={"team_a": "UCAM Esports", "team_b": "Barca eSports"}
    )

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["role"] == "DUELO DE MID"
    assert body[0]["subject"] == "Escik vs Fulano"
    assert "Escik" in body[0]["content"]
    assert "Fulano" in body[0]["content"]
    assert body[0]["suggested_teams"] == ["UCAM Esports", "Barca eSports"]


def test_generate_duel_no_common_role_returns_empty_list(client, mocker):
    _mock_success(mocker, roster_a=[RosterPlayer(name="Escik", role="mid")], roster_b=[RosterPlayer(name="Fulano", role="top")])

    res = client.post("/api/generate/duel", json={"team_a": "UCAM Esports", "team_b": "Barca eSports"})

    assert res.status_code == 200
    assert res.json() == []


def test_generate_duel_requires_both_teams(client):
    res = client.post("/api/generate/duel", json={"team_a": "UCAM Esports"})
    assert res.status_code == 422


def test_generate_duel_rejects_same_team(client):
    res = client.post(
        "/api/generate/duel", json={"team_a": "UCAM Esports", "team_b": "ucam esports"}
    )
    assert res.status_code == 400




def test_generate_duel_unknown_team_returns_400(client, mocker):
    mocker.patch(
        "app.routers.generate.duel.fetch_les_team_roster_with_roles",
        side_effect=TeamRosterNotFoundError("No encontramos el equipo 'X' en la LES."),
    )

    res = client.post(
        "/api/generate/duel", json={"team_a": "Un Equipo Que No Existe", "team_b": "Barca eSports"}
    )

    assert res.status_code == 400


def test_generate_duel_lolesports_failure_returns_502(client, mocker):
    mocker.patch(
        "app.routers.generate.duel.fetch_les_team_roster_with_roles",
        side_effect=LoLEsportsError("no se pudo obtener"),
    )

    res = client.post("/api/generate/duel", json={"team_a": "UCAM Esports", "team_b": "Barca eSports"})

    assert res.status_code == 502


def test_generate_duel_golgg_failure_returns_502(client, mocker):
    mocker.patch(
        "app.routers.generate.duel.fetch_les_team_roster_with_roles",
        side_effect=lambda name: _roster_a() if "UCAM" in name else _roster_b(),
    )
    mocker.patch("app.routers.generate.duel.fetch_player_stats", side_effect=GolGGError("no se pudo obtener"))

    res = client.post("/api/generate/duel", json={"team_a": "UCAM Esports", "team_b": "Barca eSports"})

    assert res.status_code == 502




def test_generate_duel_appends_closing_tags_with_team_handles(client, mocker):
    _mock_success(mocker)

    res = client.post("/api/generate/duel", json={"team_a": "UCAM Esports", "team_b": "Barca eSports"})

    content = res.json()[0]["content"]
    assert "@UCAM_esports" in content
    assert "@FCBeSports" in content
    assert "@LESESPORTS" in content
    assert "#LT" in content


def test_generate_duel_reconciles_summoner_name_casing(client, mocker):
    mocker.patch(
        "app.routers.generate.duel.fetch_les_team_roster_with_roles",
        side_effect=lambda name: [RosterPlayer(name="ESCIK", role="mid")]
        if "UCAM" in name
        else [RosterPlayer(name="FULANO", role="mid")],
    )
    mocker.patch(
        "app.routers.generate.duel.fetch_player_stats",
        return_value=[_player("Escik"), _player("Fulano", kda=4.0)],
    )

    res = client.post("/api/generate/duel", json={"team_a": "UCAM Esports", "team_b": "Barca eSports"})

    content = res.json()[0]["content"]
    assert "Escik" in content
    assert "ESCIK" not in content


def _match_info(team1, team2, block_name="Semana 6"):
    return MatchInfo(
        start_time=datetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc),
        state="unstarted",
        league_slug="les",
        block_name=block_name,
        team1_name=team1,
        team1_code=team1[:3].upper(),
        team2_name=team2,
        team2_code=team2[:3].upper(),
    )


def test_duel_today_match_endpoint_returns_matches(client, mocker):
    mocker.patch(
        "app.routers.generate.duel.fetch_matches_today_or_tomorrow",
        return_value=[_match_info("UCAM Esports", "Barca eSports")],
    )

    res = client.get("/api/generate/duel/today-match")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["team_a"] == "UCAM Esports"
    assert body[0]["team_b"] == "Barca eSports"


def test_duel_today_match_endpoint_empty_when_none(client, mocker):
    mocker.patch("app.routers.generate.duel.fetch_matches_today_or_tomorrow", return_value=[])

    res = client.get("/api/generate/duel/today-match")

    assert res.status_code == 200
    assert res.json() == []


def test_duel_today_match_endpoint_error_returns_502(client, mocker):
    mocker.patch(
        "app.routers.generate.duel.fetch_matches_today_or_tomorrow",
        side_effect=LoLEsportsError("no se pudo obtener"),
    )

    res = client.get("/api/generate/duel/today-match")

    assert res.status_code == 502
