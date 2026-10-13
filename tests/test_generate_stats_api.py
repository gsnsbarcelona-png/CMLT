from app.services.golgg_service import GolGGError, PlayerStat, StatFocusNotFoundError, TeamStat
from app.services.lolesports_service import TeamRosterNotFoundError
from app.services.ranked_service import PlayerRank, RankedError


def _team():
    return TeamStat(name="UCAM Esports", games=15, win_rate=86.7, kda=2.13, gpm=2157, fb_pct=66.7, towers_killed=8.9)


def _player():
    return PlayerStat(name="Escik", games=15, win_rate=86.7, kda=9.4, csm=9.2, avg_kills=6.7, penta_kills=0, solo_kills=8)


def _mock_no_h2h(mocker):
    """La mayoria de los tests no le interesa el head-to-head -- lo mockeamos
    vacio para no pegarle a gol.gg de verdad cuando 'teams' esta en categories."""
    return mocker.patch("app.routers.generate.compute_head_to_head_candidates", return_value=[])


def test_generate_stats_plain_success(client, mocker):
    mocker.patch("app.routers.generate.fetch_team_stats", return_value=[_team()])
    mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])
    _mock_no_h2h(mocker)

    res = client.post("/api/generate/stats", json={"categories": ["teams", "players"]})

    assert res.status_code == 200
    body = res.json()
    assert body["char_count"] > 0
    assert body["content"]


def test_generate_stats_only_fetches_requested_categories(client, mocker):
    team_mock = mocker.patch("app.routers.generate.fetch_team_stats", return_value=[_team()])
    player_mock = mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])

    client.post("/api/generate/stats", json={"categories": ["players"]})

    team_mock.assert_not_called()
    player_mock.assert_called_once()


def test_generate_stats_requires_category(client):
    res = client.post("/api/generate/stats", json={"categories": []})
    assert res.status_code == 400


def test_generate_stats_rejects_unknown_category(client):
    res = client.post("/api/generate/stats", json={"categories": ["coaches"]})
    assert res.status_code == 400




def test_generate_stats_rejects_unknown_scope(client, mocker):
    mocker.patch("app.routers.generate.fetch_team_stats", return_value=[_team()])

    res = client.post("/api/generate/stats", json={"categories": ["teams"], "scope": "decade"})
    assert res.status_code == 400


def test_generate_stats_focus_with_match(client, mocker):
    mocker.patch("app.routers.generate.fetch_team_stats", return_value=[])
    mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])
    _mock_no_h2h(mocker)

    res = client.post(
        "/api/generate/stats", json={"categories": ["teams", "players"], "focus": "Escik"}
    )

    assert res.status_code == 200
    assert "Escik" in res.json()["content"]


def test_generate_stats_focus_not_found_returns_400(client, mocker):
    mocker.patch("app.routers.generate.fetch_team_stats", return_value=[_team()])
    mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])
    _mock_no_h2h(mocker)

    res = client.post(
        "/api/generate/stats", json={"categories": ["teams", "players"], "focus": "nadie"}
    )

    assert res.status_code == 400


def test_generate_stats_golgg_failure_returns_502(client, mocker):
    mocker.patch("app.routers.generate.fetch_team_stats", side_effect=GolGGError("no se pudo obtener"))

    res = client.post("/api/generate/stats", json={"categories": ["teams"]})

    assert res.status_code == 502






def test_generate_stats_scope_year_uses_aggregate_functions(client, mocker):
    agg_team_mock = mocker.patch("app.routers.generate.aggregate_team_stats", return_value=[_team()])
    agg_player_mock = mocker.patch("app.routers.generate.aggregate_player_stats", return_value=[_player()])
    split_team_mock = mocker.patch("app.routers.generate.fetch_team_stats")
    split_player_mock = mocker.patch("app.routers.generate.fetch_player_stats")
    _mock_no_h2h(mocker)

    res = client.post(
        "/api/generate/stats", json={"categories": ["teams", "players"], "scope": "year"}
    )

    assert res.status_code == 200
    agg_team_mock.assert_called_once()
    agg_player_mock.assert_called_once()
    split_team_mock.assert_not_called()
    split_player_mock.assert_not_called()


def test_generate_stats_head_to_head_only_when_teams_selected(client, mocker):
    mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])
    h2h_mock = _mock_no_h2h(mocker)

    res = client.post("/api/generate/stats", json={"categories": ["players"]})

    assert res.status_code == 200
    h2h_mock.assert_not_called()


def test_list_stat_teams(client, mocker):
    mocker.patch("app.routers.generate.fetch_team_stats", return_value=[_team(), _team()])

    res = client.get("/api/generate/stats/teams")

    assert res.status_code == 200
    assert res.json() == ["UCAM Esports", "UCAM Esports"]


def test_list_stat_teams_golgg_failure_returns_502(client, mocker):
    mocker.patch("app.routers.generate.fetch_team_stats", side_effect=GolGGError("no se pudo obtener"))

    res = client.get("/api/generate/stats/teams")

    assert res.status_code == 502


def test_list_available_tournaments(client, mocker):
    discover_mock = mocker.patch(
        "app.routers.generate.discover_tournaments",
        return_value=[{"trname": "LES 2026 Summer", "region": "ES", "nbgames": "63"}],
    )

    res = client.get("/api/generate/stats/available-tournaments?season=S16&region=ES")

    assert res.status_code == 200
    assert res.json() == [{"trname": "LES 2026 Summer", "region": "ES", "nbgames": "63"}]
    discover_mock.assert_called_once_with("S16", "ES")


def test_list_available_tournaments_golgg_failure_returns_502(client, mocker):
    mocker.patch(
        "app.routers.generate.discover_tournaments", side_effect=GolGGError("no se pudo consultar")
    )

    res = client.get("/api/generate/stats/available-tournaments")

    assert res.status_code == 502


def _fake_h2h_candidate():
    from app.services.golgg_service import StatCandidate

    return StatCandidate(
        kind="team_head_to_head",
        subject="Barca eSports vs UCAM Esports",
        fact_sentence="UCAM Esports le gano a Barca eSports en 2 de sus 3 cruces esta temporada (2-1).",
        plano_emoji="🤜🤛",
        plano_title="RIVALIDAD DEL AÑO",
        plano_question="¿Se repite la historia la proxima vez que se crucen?",
    )


def test_generate_stats_rivalry_pair_success(client, mocker):
    mocker.patch("app.routers.generate.find_head_to_head", return_value=_fake_h2h_candidate())

    res = client.post(
        "/api/generate/stats",
        json={"rivalry_team_a": "UCAM Esports", "rivalry_team_b": "Barca eSports"},
    )

    assert res.status_code == 200
    assert "UCAM Esports" in res.json()["content"]


def test_generate_stats_rivalry_pair_requires_both_teams(client):
    res = client.post("/api/generate/stats", json={"rivalry_team_a": "UCAM Esports"})
    assert res.status_code == 400


def test_generate_stats_rivalry_pair_not_found_returns_400(client, mocker):
    mocker.patch("app.routers.generate.find_head_to_head", return_value=None)

    res = client.post(
        "/api/generate/stats",
        json={"rivalry_team_a": "UCAM Esports", "rivalry_team_b": "Barca eSports"},
    )

    assert res.status_code == 400


def test_generate_stats_rivalry_pair_ignores_categories_validation(client, mocker):
    # No hace falta mandar categories cuando se eligen los dos equipos de rivalidad.
    mocker.patch("app.routers.generate.find_head_to_head", return_value=_fake_h2h_candidate())

    res = client.post(
        "/api/generate/stats",
        json={"categories": [], "rivalry_team_a": "UCAM Esports", "rivalry_team_b": "Barca eSports"},
    )

    assert res.status_code == 200


def test_generate_stats_appends_closing_tags_with_team_handles(client, mocker):
    mocker.patch("app.routers.generate.find_head_to_head", return_value=_fake_h2h_candidate())

    res = client.post(
        "/api/generate/stats",
        json={"rivalry_team_a": "UCAM Esports", "rivalry_team_b": "Barca eSports"},
    )

    content = res.json()["content"]
    assert "@UCAM_esports" in content
    assert "@FCBeSports" in content
    assert "@LESESPORTS" in content
    assert "#LT" in content


def test_generate_stats_rivalry_pair_golgg_failure_returns_502(client, mocker):
    mocker.patch(
        "app.routers.generate.find_head_to_head", side_effect=GolGGError("no se pudo obtener")
    )

    res = client.post(
        "/api/generate/stats",
        json={"rivalry_team_a": "UCAM Esports", "rivalry_team_b": "Barca eSports"},
    )

    assert res.status_code == 502


def _rank():
    return PlayerRank(
        player="Escik", slug="escik", tier="Challenger", lp=2698, wins=281, losses=189, date="28/08",
        peak_tier="Challenger", peak_lp=2813, peak_wins=280, peak_losses=185, peak_date="16/08",
    )


def test_generate_stats_ranked_category_success(client, mocker):
    mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])
    mocker.patch(
        "app.routers.generate.fetch_all_player_ranks", return_value=([_rank()], [])
    )

    res = client.post("/api/generate/stats", json={"categories": ["ranked"]})

    assert res.status_code == 200
    assert "Escik" in res.json()["content"]


def test_generate_stats_ranked_reuses_already_fetched_player_stats(client, mocker):
    player_mock = mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])
    mocker.patch("app.routers.generate.fetch_all_player_ranks", return_value=([_rank()], []))

    client.post("/api/generate/stats", json={"categories": ["players", "ranked"]})

    # Se pide una sola vez: el roster para "ranked" reusa el fetch de "players".
    player_mock.assert_called_once()


def test_generate_stats_ranked_failure_returns_502(client, mocker):
    mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])
    mocker.patch(
        "app.routers.generate.fetch_all_player_ranks", side_effect=RankedError("no se pudo consultar")
    )

    res = client.post("/api/generate/stats", json={"categories": ["ranked"]})

    assert res.status_code == 502


def test_generate_stats_ranked_focus_targets_player(client, mocker):
    other_rank = PlayerRank(
        player="Andariel", slug="andariel", tier="Grandmaster", lp=900, wins=20, losses=15, date="20/08",
    )
    mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])
    mocker.patch(
        "app.routers.generate.fetch_all_player_ranks", return_value=([_rank(), other_rank], [])
    )

    res = client.post(
        "/api/generate/stats", json={"categories": ["ranked"], "focus": "Escik"}
    )

    assert res.status_code == 200
    assert "Escik" in res.json()["content"]


def _rank_for(player, tier="Gold", lp=20):
    return PlayerRank(player=player, slug=player.lower(), tier=tier, lp=lp, wins=10, losses=5, date="01/01")


def test_generate_stats_ranked_player_vs_player_success(client, mocker):
    mocker.patch(
        "app.routers.generate.fetch_player_rank",
        side_effect=lambda name: _rank_for(name, "Challenger", 2698) if name == "Escik" else _rank_for(name),
    )

    res = client.post(
        "/api/generate/stats",
        json={"ranked_player_a": "Escik", "ranked_player_b": "Andariel"},
    )

    assert res.status_code == 200
    body = res.json()
    assert "Escik" in body["content"]
    assert "Andariel" in body["content"]


def test_generate_stats_ranked_player_vs_player_requires_both(client):
    res = client.post("/api/generate/stats", json={"ranked_player_a": "Escik"})
    assert res.status_code == 400


def test_generate_stats_ranked_player_vs_player_rejects_same_player(client):
    res = client.post(
        "/api/generate/stats",
        json={"ranked_player_a": "Escik", "ranked_player_b": "escik"},
    )
    assert res.status_code == 400


def test_generate_stats_ranked_player_vs_player_not_found_returns_400(client, mocker):
    mocker.patch(
        "app.routers.generate.fetch_player_rank",
        side_effect=lambda name: _rank_for(name) if name == "Escik" else None,
    )

    res = client.post(
        "/api/generate/stats",
        json={"ranked_player_a": "Escik", "ranked_player_b": "NadieConEsteNombre"},
    )

    assert res.status_code == 400
    assert "NadieConEsteNombre" in res.json()["detail"]


def test_generate_stats_ranked_player_vs_player_network_error_returns_502(client, mocker):
    mocker.patch("app.routers.generate.fetch_player_rank", side_effect=RankedError("no se pudo consultar"))

    res = client.post(
        "/api/generate/stats",
        json={"ranked_player_a": "Escik", "ranked_player_b": "Andariel"},
    )

    assert res.status_code == 502


def test_generate_stats_ranked_team_vs_team_success(client, mocker):
    mocker.patch(
        "app.routers.generate.fetch_les_team_roster",
        side_effect=lambda name: ["Escik", "Kozi"] if "UCAM" in name else ["Andariel"],
    )
    mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])
    mocker.patch(
        "app.routers.generate.fetch_all_player_ranks",
        side_effect=lambda names: ([_rank_for(n) for n in names], []),
    )

    res = client.post(
        "/api/generate/stats",
        json={"ranked_team_a": "UCAM Esports", "ranked_team_b": "Barca eSports"},
    )

    assert res.status_code == 200
    content = res.json()["content"]
    assert "@UCAM_esports" in content
    assert "@FCBeSports" in content


def test_generate_stats_ranked_team_vs_team_fixes_summoner_name_casing(client, mocker):
    # El roster de lolesports.com viene en MAYUSCULAS (ej. "ESCIK"); se
    # reconcilia con la capitalizacion real de gol.gg antes de mostrarlo.
    mocker.patch(
        "app.routers.generate.fetch_les_team_roster",
        side_effect=lambda name: ["ESCIK"] if "UCAM" in name else ["ANDARIEL"],
    )
    mocker.patch(
        "app.routers.generate.fetch_player_stats",
        return_value=[_player(), PlayerStat(name="Andariel", games=15, win_rate=50.0, kda=3.0, csm=8.0, avg_kills=3.0, penta_kills=0, solo_kills=1)],
    )
    mocker.patch(
        "app.routers.generate.fetch_all_player_ranks",
        side_effect=lambda names: ([_rank_for(n) for n in names], []),
    )

    res = client.post(
        "/api/generate/stats",
        json={"ranked_team_a": "UCAM Esports", "ranked_team_b": "Barca eSports"},
    )

    content = res.json()["content"]
    assert "Escik" in content
    assert "ESCIK" not in content
    assert "Andariel" in content
    assert "ANDARIEL" not in content


def test_generate_stats_ranked_team_vs_team_casing_falls_back_when_golgg_fails(client, mocker):
    mocker.patch("app.routers.generate.fetch_les_team_roster", return_value=["ESCIK"])
    mocker.patch("app.routers.generate.fetch_player_stats", side_effect=GolGGError("no se pudo obtener"))
    mocker.patch(
        "app.routers.generate.fetch_all_player_ranks",
        side_effect=lambda names: ([_rank_for(n) for n in names], []),
    )

    res = client.post(
        "/api/generate/stats",
        json={"ranked_team_a": "UCAM Esports", "ranked_team_b": "Barca eSports"},
    )

    assert res.status_code == 200
    assert "ESCIK" in res.json()["content"]


def test_generate_stats_ranked_team_vs_team_requires_both(client):
    res = client.post("/api/generate/stats", json={"ranked_team_a": "UCAM Esports"})
    assert res.status_code == 400


def test_generate_stats_ranked_team_vs_team_rejects_same_team(client):
    res = client.post(
        "/api/generate/stats",
        json={"ranked_team_a": "UCAM Esports", "ranked_team_b": "ucam esports"},
    )
    assert res.status_code == 400


def test_generate_stats_ranked_team_vs_team_unknown_team_returns_400(client, mocker):
    mocker.patch(
        "app.routers.generate.fetch_les_team_roster",
        side_effect=TeamRosterNotFoundError("No encontramos el equipo 'X' en la LES."),
    )

    res = client.post(
        "/api/generate/stats",
        json={"ranked_team_a": "Un Equipo Que No Existe", "ranked_team_b": "Barca eSports"},
    )

    assert res.status_code == 400


def test_generate_stats_ranked_team_vs_team_no_ranks_resolved_returns_502(client, mocker):
    mocker.patch("app.routers.generate.fetch_les_team_roster", return_value=["Alguien"])
    mocker.patch("app.routers.generate.fetch_player_stats", return_value=[_player()])
    mocker.patch("app.routers.generate.fetch_all_player_ranks", return_value=([], ["Alguien"]))

    res = client.post(
        "/api/generate/stats",
        json={"ranked_team_a": "UCAM Esports", "ranked_team_b": "Barca eSports"},
    )

    assert res.status_code == 502
