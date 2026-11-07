from app.services.golgg_service import GolGGError, PlayerStat, TeamStat


def _players():
    return [
        PlayerStat(name="Escik", games=15, win_rate=86.7, kda=9.4, csm=9.2, avg_kills=6.7, penta_kills=0, solo_kills=8),
        PlayerStat(name="Andariel", games=15, win_rate=86.7, kda=7.7, csm=9.3, avg_kills=6.1, penta_kills=0, solo_kills=8),
    ]


def _teams():
    return [
        TeamStat(
            name="UCAM Esports", games=15, win_rate=86.7, kda=2.13, gpm=2157, fb_pct=66.7, towers_killed=8.9,
            dragons_per_game=2.5, avg_game_duration_seconds=29 * 60 + 10,
        ),
        TeamStat(
            name="Barca eSports", games=16, win_rate=56.3, kda=1.22, gpm=2012, fb_pct=62.5, towers_killed=7.5,
            dragons_per_game=2.63, avg_game_duration_seconds=32 * 60 + 37,
        ),
    ]


def test_list_top_ranking_categories(client):
    res = client.get("/api/generate/top-ranking/categories")

    assert res.status_code == 200
    body = res.json()
    assert body["player_kda"] == "KDA"
    assert body["team_fastest"] == "Equipos que mas rapido cierran sus partidas"


def test_generate_top_ranking_player_category_success(client, mocker):
    mocker.patch("app.routers.generate.top_ranking.fetch_player_stats", return_value=_players())

    res = client.post("/api/generate/top-ranking", json={"category": "player_kda"})

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    variants = {r["variant"] for r in body}
    assert variants == {"top1", "top3"}
    top1 = next(r for r in body if r["variant"] == "top1")
    top3 = next(r for r in body if r["variant"] == "top3")
    assert "Escik" in top1["content"]
    assert "Escik" in top3["content"]
    assert "Andariel" in top3["content"]
    assert top1["error"] is None
    assert top1["suggested_teams"] == []  # gol.gg no da equipo por jugador -- nunca se inventa


def test_generate_top_ranking_team_category_success(client, mocker):
    mocker.patch("app.routers.generate.top_ranking.fetch_team_stats", return_value=_teams())

    res = client.post("/api/generate/top-ranking", json={"category": "team_towers"})

    assert res.status_code == 200
    body = res.json()
    assert all(r["content"] for r in body)
    assert all(r["suggested_teams"] == ["UCAM Esports"] for r in body)  # el lider (mas torres/partida)


def test_generate_top_ranking_only_fetches_needed_level(client, mocker):
    # Categoria de jugador: no deberia llamar a fetch_team_stats en absoluto.
    team_mock = mocker.patch("app.routers.generate.top_ranking.fetch_team_stats")
    mocker.patch("app.routers.generate.top_ranking.fetch_player_stats", return_value=_players())

    res = client.post("/api/generate/top-ranking", json={"category": "player_csm"})

    assert res.status_code == 200
    team_mock.assert_not_called()


def test_generate_top_ranking_unknown_category_returns_400(client):
    res = client.post("/api/generate/top-ranking", json={"category": "no_existe"})
    assert res.status_code == 400


def test_generate_top_ranking_unknown_style_returns_400(client, mocker):
    mocker.patch("app.routers.generate.top_ranking.fetch_player_stats", return_value=_players())

    res = client.post("/api/generate/top-ranking", json={"category": "player_kda", "style": "flashy"})

    assert res.status_code == 400


def test_generate_top_ranking_golgg_failure_returns_502(client, mocker):
    mocker.patch("app.routers.generate.top_ranking.fetch_player_stats", side_effect=GolGGError("no se pudo obtener"))

    res = client.post("/api/generate/top-ranking", json={"category": "player_kda"})

    assert res.status_code == 502


def test_generate_top_ranking_ai_style_uses_ai(client, mocker):
    mocker.patch("app.routers.generate.top_ranking.fetch_player_stats", return_value=_players())
    ai_mock = mocker.patch("app.routers.generate.top_ranking.generate_top_ranking_variant", return_value="Top con onda!")

    res = client.post("/api/generate/top-ranking", json={"category": "player_kda", "style": "ai"})

    assert res.status_code == 200
    body = res.json()
    assert all(r["content"].startswith("Top con onda!") for r in body)
    assert ai_mock.call_count == 2


def test_generate_top_ranking_team_category_includes_leader_team_handle(client, mocker, monkeypatch):
    from app.services import golgg_service

    monkeypatch.setattr(golgg_service.settings, "team_handles", "UCAM Esports:@UCAMEsports")
    mocker.patch("app.routers.generate.top_ranking.fetch_team_stats", return_value=_teams())

    res = client.post("/api/generate/top-ranking", json={"category": "team_towers"})

    assert res.status_code == 200
    assert "@UCAMEsports" in res.json()[0]["content"]


def test_generate_top_ranking_player_category_has_no_team_handle(client, mocker, monkeypatch):
    from app.services import golgg_service

    monkeypatch.setattr(golgg_service.settings, "team_handles", "Escik:@EscikTeam")
    mocker.patch("app.routers.generate.top_ranking.fetch_player_stats", return_value=_players())

    res = client.post("/api/generate/top-ranking", json={"category": "player_kda"})

    assert res.status_code == 200
    assert "@EscikTeam" not in res.json()[0]["content"]
