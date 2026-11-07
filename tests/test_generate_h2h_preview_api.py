from datetime import datetime, timezone

from app.services.ai_service import AIGenerationError
from app.services.golgg_service import GolGGError, HeadToHeadPreviewData, TeamStat
from app.services.lolesports_service import LoLEsportsError, MatchInfo


def _team(name):
    return TeamStat(
        name=name, games=1, win_rate=50.0, kda=2.0, gpm=2000, fb_pct=50.0, towers_killed=5.0,
        dragons_per_game=2.0, avg_game_duration_seconds=1800,
    )


def _preview():
    return HeadToHeadPreviewData(
        team_a="UCAM Esports",
        team_b="Barca eSports",
        total_wins_a=1,
        total_wins_b=1,
        total_maps_a=3,
        total_maps_b=2,
        last_meeting=None,
        last_win_by_a=None,
        last_win_by_b=None,
        recent_form_a=None,
        recent_form_b=None,
    )


def _mock_today_no_match(mocker):
    return mocker.patch("app.routers.generate.stats.fetch_todays_matches", return_value=[])


def test_h2h_preview_ai_style_does_not_save_drafts(client, mocker):
    # El preview ya no auto-guarda -- el usuario elige que variante guardar
    # con el boton "Guardar" de su tarjeta (POST /api/tweets).
    mocker.patch("app.routers.generate.stats.build_head_to_head_preview", return_value=_preview())
    _mock_today_no_match(mocker)
    ai_mock = mocker.patch(
        "app.routers.generate.stats.generate_head_to_head_variant",
        side_effect=["Variante historial", "Variante forma"],
    )

    res = client.post(
        "/api/generate/stats/head-to-head-preview",
        json={"team_a": "UCAM Esports", "team_b": "Barca eSports", "style": "ai"},
    )

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["angle"] == "historial"
    assert body[0]["content"].startswith("Variante historial")
    assert "draft_id" not in body[0]
    assert body[1]["angle"] == "forma_reciente"
    assert body[1]["content"].startswith("Variante forma")
    assert body[0]["suggested_teams"] == ["UCAM Esports", "Barca eSports"]
    assert body[1]["suggested_teams"] == ["UCAM Esports", "Barca eSports"]
    assert ai_mock.call_count == 2

    drafts = client.get("/api/tweets?status=draft").json()
    assert len(drafts) == 0


def test_h2h_preview_default_style_is_plain_and_skips_ai(client, mocker):
    mocker.patch("app.routers.generate.stats.build_head_to_head_preview", return_value=_preview())
    _mock_today_no_match(mocker)
    ai_mock = mocker.patch("app.routers.generate.stats.generate_head_to_head_variant")

    res = client.post(
        "/api/generate/stats/head-to-head-preview",
        json={"team_a": "UCAM Esports", "team_b": "Barca eSports"},
    )

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert all(item["error"] is None for item in body)
    ai_mock.assert_not_called()


def test_h2h_preview_rejects_unknown_style(client, mocker):
    mocker.patch("app.routers.generate.stats.build_head_to_head_preview", return_value=_preview())

    res = client.post(
        "/api/generate/stats/head-to-head-preview",
        json={"team_a": "UCAM Esports", "team_b": "Barca eSports", "style": "flashy"},
    )

    assert res.status_code == 400


def test_h2h_preview_requires_both_teams(client):
    # team_b es un campo requerido del modelo -> FastAPI/pydantic devuelve 422
    # antes de que el endpoint llegue a correr su propia validacion.
    res = client.post("/api/generate/stats/head-to-head-preview", json={"team_a": "UCAM Esports"})
    assert res.status_code == 422


def test_h2h_preview_rejects_same_team_twice(client):
    res = client.post(
        "/api/generate/stats/head-to-head-preview",
        json={"team_a": "UCAM Esports", "team_b": "ucam esports"},
    )
    assert res.status_code == 400


def test_h2h_preview_golgg_failure_returns_502(client, mocker):
    mocker.patch(
        "app.routers.generate.stats.build_head_to_head_preview", side_effect=GolGGError("no se pudo obtener")
    )

    res = client.post(
        "/api/generate/stats/head-to-head-preview",
        json={"team_a": "UCAM Esports", "team_b": "Barca eSports"},
    )

    assert res.status_code == 502


def test_h2h_preview_partial_ai_failure_still_returns_the_other_variant(client, mocker):
    mocker.patch("app.routers.generate.stats.build_head_to_head_preview", return_value=_preview())
    _mock_today_no_match(mocker)
    mocker.patch(
        "app.routers.generate.stats.generate_head_to_head_variant",
        side_effect=[AIGenerationError("Falta configurar ANTHROPIC_API_KEY"), "Variante forma"],
    )

    res = client.post(
        "/api/generate/stats/head-to-head-preview",
        json={"team_a": "UCAM Esports", "team_b": "Barca eSports", "style": "ai"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body[0]["angle"] == "historial"
    assert body[0]["error"] is not None
    assert body[0]["content"] is None
    assert body[1]["angle"] == "forma_reciente"
    assert body[1]["error"] is None
    assert body[1]["content"].startswith("Variante forma")


def _match_info(team1, team2, block_name="Final"):
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


def test_h2h_preview_combines_les_and_emea_masters_tournaments(client, mocker):
    # Un equipo de LES que juega en EMEA Masters se cruza con rivales que
    # nunca jugaron en LES -- H2H necesita buscar en los dos pools de
    # torneos, no solo en LES, para no devolver historial/forma vacios.
    bhp_mock = mocker.patch("app.routers.generate.stats.build_head_to_head_preview", return_value=_preview())
    _mock_today_no_match(mocker)
    mocker.patch("app.routers.generate.stats.get_year_tournaments", return_value=["LES 2026 Summer"])
    mocker.patch(
        "app.routers.generate.stats.get_emea_masters_tournaments",
        return_value=["EMEA Masters 2026 Spring Main Event"],
    )

    client.post(
        "/api/generate/stats/head-to-head-preview",
        json={"team_a": "UCAM Esports", "team_b": "Karmine Corp Blue"},
    )

    bhp_mock.assert_called_once_with(
        "UCAM Esports", "Karmine Corp Blue", ["LES 2026 Summer", "EMEA Masters 2026 Spring Main Event"]
    )


def test_h2h_preview_today_context_checks_emea_masters_league_too(client, mocker):
    mocker.patch("app.routers.generate.stats.build_head_to_head_preview", return_value=_preview())
    today_mock = mocker.patch("app.routers.generate.stats.fetch_todays_matches", return_value=[])

    client.post(
        "/api/generate/stats/head-to-head-preview",
        json={"team_a": "UCAM Esports", "team_b": "Barca eSports"},
    )

    today_mock.assert_called_once_with(["les", "emea_masters"])


def test_h2h_preview_includes_today_context_with_accent_insensitive_match(client, mocker):
    mocker.patch("app.routers.generate.stats.build_head_to_head_preview", return_value=_preview())
    mocker.patch(
        "app.routers.generate.stats.fetch_todays_matches",
        return_value=[_match_info("UCAM Esports Club", "Barça Esports")],
    )
    ai_mock = mocker.patch("app.routers.generate.stats.generate_head_to_head_variant", return_value="ok")

    client.post(
        "/api/generate/stats/head-to-head-preview",
        json={"team_a": "UCAM Esports", "team_b": "Barca eSports", "style": "ai"},
    )

    context_arg = ai_mock.call_args_list[0].args[0]
    assert "Partido de hoy" in context_arg
    assert "Final" in context_arg


def test_today_match_endpoint_returns_matches(client, mocker):
    mocker.patch(
        "app.routers.generate.stats.fetch_todays_matches",
        return_value=[_match_info("UCAM Esports", "Barca eSports", block_name="Semana 6")],
    )

    res = client.get("/api/generate/stats/today-match")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["team_a"] == "UCAM Esports"
    assert body[0]["team_b"] == "Barca eSports"
    assert body[0]["block_name"] == "Semana 6"


def test_today_match_endpoint_empty_when_none(client, mocker):
    mocker.patch("app.routers.generate.stats.fetch_todays_matches", return_value=[])

    res = client.get("/api/generate/stats/today-match")

    assert res.status_code == 200
    assert res.json() == []


def test_today_match_endpoint_error_returns_502(client, mocker):
    mocker.patch(
        "app.routers.generate.stats.fetch_todays_matches", side_effect=LoLEsportsError("no se pudo obtener")
    )

    res = client.get("/api/generate/stats/today-match")

    assert res.status_code == 502


def test_h2h_teams_combines_les_and_emea_masters(client, mocker):
    mocker.patch(
        "app.routers.generate.stats.get_emea_masters_tournaments", return_value=["EMEA Masters 2026 Spring"]
    )
    mocker.patch(
        "app.routers.generate.stats.fetch_team_stats",
        side_effect=lambda tournament=None: [_team("UCAM Esports")]
        if tournament is None
        else [_team("Karmine Corp Blue"), _team("UCAM Esports")],
    )

    res = client.get("/api/generate/stats/h2h-teams")

    assert res.status_code == 200
    assert res.json() == ["Karmine Corp Blue", "UCAM Esports"]


def test_h2h_teams_les_failure_returns_502(client, mocker):
    mocker.patch("app.routers.generate.stats.fetch_team_stats", side_effect=GolGGError("no se pudo obtener"))

    res = client.get("/api/generate/stats/h2h-teams")

    assert res.status_code == 502


def test_h2h_teams_skips_failing_emea_masters_tournament(client, mocker):
    # Best-effort: un torneo de EMEA Masters que falle (mal configurado, gol.gg
    # caido para esa pagina puntual) no debe tumbar el resto de la lista.
    mocker.patch(
        "app.routers.generate.stats.get_emea_masters_tournaments",
        return_value=["Torneo Que No Existe"],
    )
    mocker.patch(
        "app.routers.generate.stats.fetch_team_stats",
        side_effect=lambda tournament=None: [_team("UCAM Esports")]
        if tournament is None
        else (_ for _ in ()).throw(GolGGError("no se pudo obtener")),
    )

    res = client.get("/api/generate/stats/h2h-teams")

    assert res.status_code == 200
    assert res.json() == ["UCAM Esports"]
