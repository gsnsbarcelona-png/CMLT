from app.services.crossover_service import CrossoverDataError
from app.services.golgg_service import GolGGError, PlayerStat, TeamStat


def _les_team():
    return TeamStat(
        name="UCAM Esports", games=15, win_rate=86.7, kda=2.13, gpm=2157, fb_pct=66.7, towers_killed=8.9,
        dragons_per_game=2.5, avg_game_duration_seconds=1750,
    )


def _lec_team():
    return TeamStat(
        name="Fnatic", games=20, win_rate=50.0, kda=1.5, gpm=2100, fb_pct=55.0, towers_killed=8.0,
        dragons_per_game=2.2, avg_game_duration_seconds=1800,
    )


def _les_player():
    return PlayerStat(name="Escik", games=15, win_rate=86.7, kda=9.4, csm=9.2, avg_kills=6.7, penta_kills=0, solo_kills=8)


def _lec_player():
    return PlayerStat(name="Caps", games=20, win_rate=55.0, kda=4.0, csm=9.5, avg_kills=4.5, penta_kills=0, solo_kills=2)


def _mock_fetches(mocker):
    mocker.patch("app.routers.generate.league_comparison.fetch_team_stats", side_effect=[[_les_team()], [_lec_team()]])
    mocker.patch("app.routers.generate.league_comparison.fetch_player_stats", side_effect=[[_les_player()], [_lec_player()]])


def test_league_comparison_returns_two_tones_and_does_not_save_drafts(client, mocker):
    # La comparativa LES-LEC ya no auto-guarda -- el usuario elige que tono
    # guardar con el boton "Guardar" de su tarjeta (POST /api/tweets).
    _mock_fetches(mocker)

    res = client.post("/api/generate/league-comparison", json={})

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["tone"] == "sorprendente"
    assert body[1]["tone"] == "debate"
    assert "draft_id" not in body[0]

    drafts = client.get("/api/tweets?status=draft").json()
    assert len(drafts) == 0






def test_league_comparison_focus_with_match(client, mocker):
    _mock_fetches(mocker)

    res = client.post("/api/generate/league-comparison", json={"focus": "UCAM"})

    assert res.status_code == 200
    assert "UCAM Esports" in res.json()[0]["content"]


def test_league_comparison_suggests_team_for_team_candidate(client, mocker):
    _mock_fetches(mocker)

    res = client.post("/api/generate/league-comparison", json={"focus": "UCAM"})

    assert res.json()[0]["suggested_teams"] == ["UCAM Esports"]


def test_league_comparison_no_suggestion_for_player_candidate(client, mocker):
    mocker.patch("app.routers.generate.league_comparison.fetch_team_stats", side_effect=GolGGError("no se pudo obtener"))

    res = client.post("/api/generate/league-comparison", json={"focus": "Flakked"})

    assert res.json()[0]["suggested_teams"] == []


def test_league_comparison_focus_not_found_returns_400(client, mocker):
    _mock_fetches(mocker)

    res = client.post("/api/generate/league-comparison", json={"focus": "nadie con este nombre"})

    assert res.status_code == 400


def test_league_comparison_golgg_failure_falls_back_to_crossover_candidates(client, mocker):
    # gol.gg caido no tumba el endpoint entero -- la base de cruces de
    # jugadores (dato curado, no depende de gol.gg) sigue disponible.
    mocker.patch("app.routers.generate.league_comparison.fetch_team_stats", side_effect=GolGGError("no se pudo obtener"))

    res = client.post("/api/generate/league-comparison", json={"focus": "Flakked"})

    assert res.status_code == 200
    assert "Flakked" in res.json()[0]["content"]


def test_league_comparison_both_sources_failing_returns_502(client, mocker):
    mocker.patch("app.routers.generate.league_comparison.fetch_team_stats", side_effect=GolGGError("no se pudo obtener"))
    mocker.patch(
        "app.routers.generate.league_comparison.compute_player_crossover_candidates",
        side_effect=CrossoverDataError("no se pudo leer la base de cruces"),
    )

    res = client.post("/api/generate/league-comparison", json={})

    assert res.status_code == 502


def test_league_comparison_pool_includes_both_metric_and_crossover_candidates(client, mocker):
    _mock_fetches(mocker)

    res = client.post("/api/generate/league-comparison", json={"focus": "Elyoya"})

    assert res.status_code == 200
    assert "Elyoya" in res.json()[0]["content"]


def test_league_comparison_includes_closing_tags(client, mocker):
    _mock_fetches(mocker)

    res = client.post("/api/generate/league-comparison", json={"focus": "UCAM"})

    content = res.json()[0]["content"]
    assert "@UCAM_esports" in content
    assert "@LESESPORTS" in content
    assert "#LT" in content
