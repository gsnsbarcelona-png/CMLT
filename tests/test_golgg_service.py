import httpx
import pytest

from app.services.golgg_service import (
    GolGGError,
    MatchResult,
    PlayerStat,
    StatCandidate,
    StatFocusNotFoundError,
    TeamStat,
    aggregate_player_stats,
    aggregate_team_stats,
    build_head_to_head_preview,
    compute_candidates,
    compute_head_to_head_candidates,
    fetch_all_match_results,
    fetch_match_results,
    fetch_player_stats,
    fetch_team_stats,
    find_head_to_head,
    format_h2h_variant_plain,
    format_stat_tweet_plain,
    compute_league_comparison_candidates,
    discover_tournaments,
    format_league_comparison_plain,
    get_lec_tournament,
    get_team_handles,
    get_year_tournaments,
    pick_candidate,
    pick_league_comparison_candidate,
    stat_closing_tags,
)
from app.services.golgg_service import _recent_form

TEAM_HEADERS = [
    "Name", "Season", "Region", "Games", "Win rate", "K:D", "GPM", "GDM", "Game duration",
    "FP%", "Blue%", "Kills / game", "Deaths / game", "Towers killed", "Towers lost", "FB%",
]
PLAYER_HEADERS = [
    "Player", "Country", "Games", "Win rate", "KDA", "Avg kills", "Avg deaths", "Avg assists",
    "CSM", "GPM", "KP%", "DMG%", "Gold%", "VS%", "DPM", "VSPM", "Avg WPM", "Avg WCPM",
    "Avg VWPM", "GD@15", "CSD@15", "XPD@15", "FB %", "FB Victim", "Penta Kills", "Solo Kills",
]


def _row(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    header_row = "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
    body_rows = "".join(_row(r) for r in rows)
    return f'<table class="table_list playerslist tablesaw trhover">{header_row}{body_rows}</table>'


def _teams_html(rows: list[list[str]]) -> str:
    return f"<html><body>{_table(TEAM_HEADERS, rows)}</body></html>"


def _players_html(rows: list[list[str]]) -> str:
    return f"<html><body>{_table(PLAYER_HEADERS, rows)}</body></html>"


def _matchlist_html(matches, winner_in_position_3: bool = False) -> str:
    # matches: list of (winner, score, loser) o (winner, score, loser, date) --
    # misma forma que el HTML real, con headers vacios en las columnas de
    # ganador/perdedor. El ganador se marca con class="text_victory" (no por
    # posicion), igual que gol.gg real. winner_in_position_3 simula el caso
    # real donde el ganador aparece en la celda 3 en vez de la 1 (confirmado
    # que gol.gg hace esto).
    header_row = "<tr>" + "".join(f"<th>{h}</th>" for h in ["Game", "", "Score", "", "", "Patch", "Date"]) + "</tr>"
    body_rows = ""
    for match in matches:
        winner, score, loser = match[0], match[1], match[2]
        date = match[3] if len(match) > 3 else "2026-01-01"
        if winner_in_position_3:
            cell_1, cell_3 = f'<td class="text_defeat">{loser}</td>', f'<td class="text_victory">{winner}</td>'
        else:
            cell_1, cell_3 = f'<td class="text_victory">{winner}</td>', f'<td class="text_defeat">{loser}</td>'
        body_rows += (
            "<tr>"
            f"<td>X vs Y</td>{cell_1}<td>{score}</td>{cell_3}"
            f"<td>WEEK1</td><td>16.15</td><td>{date}</td>"
            "</tr>"
        )
    return f'<html><body><table class="table_list footable toggle-square-filled">{header_row}{body_rows}</table></body></html>'


TEAM_ROWS = [
    ["UCAM Esports", "S16", "ES", "15", "86.7%", "2.13", "2157", "361", "29:10", "20%", "50%", "23.3", "10.9", "8.9", "5.0", "66.7"],
    ["Barca eSports", "S16", "ES", "16", "56.3%", "1.22", "2012", "78", "32:37", "25%", "50%", "20.5", "16.8", "7.5", "5.4", "62.5"],
    ["UB Alma Mater", "S16", "ES", "16", "18.8%", "0.60", "1850", "-200", "33:00", "10%", "40%", "12.0", "20.0", "4.0", "8.0", "37.5"],
]

PLAYER_ROWS = [
    ["Escik", "PL", "15", "86.7%", "9.4", "6.7", "1.8", "10.0", "9.2", "465", "60%", "25%", "22%", "12%", "800", "1.1", "0.4", "0.2", "0.1", "50", "5", "10", "18.8%", "12%", "0", "8"],
    ["XnS", "TR", "16", "87.5%", "7.1", "5.5", "2.0", "9.8", "7.4", "460", "58%", "24%", "21%", "11%", "780", "1.0", "0.4", "0.2", "0.1", "40", "3", "8", "20%", "10%", "1", "3"],
    ["Hydra", "ES", "16", "31.3%", "2.5", "3.0", "4.0", "3.0", "8.6", "392", "40%", "18%", "18%", "9%", "500", "0.8", "0.3", "0.1", "0.1", "-20", "-3", "-5", "15%", "8%", "0", "0"],
]


def _fake_response(text: str, status_code: int = 200):
    request = httpx.Request("GET", "https://gol.gg/teams/list/")
    return httpx.Response(status_code=status_code, request=request, text=text)


def test_fetch_team_stats_parses_by_header_name(mocker):
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(_teams_html(TEAM_ROWS)))

    teams = fetch_team_stats()

    assert len(teams) == 3
    ucam = next(t for t in teams if t.name == "UCAM Esports")
    assert ucam.win_rate == 86.7
    assert ucam.kda == 2.13
    assert ucam.fb_pct == 66.7
    assert ucam.towers_killed == 8.9


def test_fetch_player_stats_parses_by_header_name(mocker):
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(_players_html(PLAYER_ROWS)))

    players = fetch_player_stats()

    assert len(players) == 3
    escik = next(p for p in players if p.name == "Escik")
    assert escik.kda == 9.4
    assert escik.csm == 9.2
    assert escik.penta_kills == 0
    assert escik.solo_kills == 8


def test_sends_browser_user_agent(mocker):
    get_mock = mocker.patch(
        "app.services.golgg_service.httpx.get", return_value=_fake_response(_teams_html(TEAM_ROWS))
    )

    fetch_team_stats()

    _, kwargs = get_mock.call_args
    assert "Mozilla" in kwargs["headers"]["User-Agent"]


def test_http_error_wrapped(mocker):
    mocker.patch("app.services.golgg_service.httpx.get", side_effect=httpx.ConnectError("boom"))

    with pytest.raises(GolGGError):
        fetch_team_stats()


def _tournaments_response(payload):
    request = httpx.Request("POST", "https://gol.gg/tournament/ajax.trlist.php")
    return httpx.Response(status_code=200, request=request, json=payload)


def test_discover_tournaments_filters_by_region(mocker):
    payload = [
        {"trname": "LES 2026 Summer", "region": "ES", "nbgames": "63"},
        {"trname": "LEC 2026 Summer Season", "region": "EUW", "nbgames": "106"},
    ]
    post_mock = mocker.patch("app.services.golgg_service.httpx.post", return_value=_tournaments_response(payload))

    tournaments = discover_tournaments(season="S16", region="ES")

    assert tournaments == [{"trname": "LES 2026 Summer", "region": "ES", "nbgames": "63"}]
    _, kwargs = post_mock.call_args
    assert kwargs["data"] == {"season": "S16"}


def test_discover_tournaments_no_region_filter_returns_all(mocker):
    payload = [
        {"trname": "LES 2026 Summer", "region": "ES", "nbgames": "63"},
        {"trname": "LEC 2026 Summer Season", "region": "EUW", "nbgames": "106"},
    ]
    mocker.patch("app.services.golgg_service.httpx.post", return_value=_tournaments_response(payload))

    tournaments = discover_tournaments(season="S16", region=None)

    assert len(tournaments) == 2


def test_discover_tournaments_defaults_season_from_settings(mocker, monkeypatch):
    import app.services.golgg_service as golgg_service

    monkeypatch.setattr(golgg_service.settings, "golgg_season", "S99")
    post_mock = mocker.patch("app.services.golgg_service.httpx.post", return_value=_tournaments_response([]))

    discover_tournaments()

    _, kwargs = post_mock.call_args
    assert kwargs["data"] == {"season": "S99"}


def test_discover_tournaments_http_error_wrapped(mocker):
    mocker.patch("app.services.golgg_service.httpx.post", side_effect=httpx.ConnectError("boom"))

    with pytest.raises(GolGGError):
        discover_tournaments(season="S16")


def test_discover_tournaments_invalid_json_wrapped(mocker):
    request = httpx.Request("POST", "https://gol.gg/tournament/ajax.trlist.php")
    bad_response = httpx.Response(status_code=200, request=request, text="not json")
    mocker.patch("app.services.golgg_service.httpx.post", return_value=bad_response)

    with pytest.raises(GolGGError):
        discover_tournaments(season="S16")


def test_repeated_calls_to_same_url_use_cache(mocker):
    get_mock = mocker.patch(
        "app.services.golgg_service.httpx.get", return_value=_fake_response(_teams_html(TEAM_ROWS))
    )

    fetch_team_stats("LES 2026 Summer")
    fetch_team_stats("LES 2026 Summer")
    fetch_team_stats("LES 2026 Summer")

    get_mock.assert_called_once()


def test_different_urls_are_not_cached_together(mocker):
    get_mock = mocker.patch(
        "app.services.golgg_service.httpx.get", return_value=_fake_response(_teams_html(TEAM_ROWS))
    )

    fetch_team_stats("LES 2026 Summer")
    fetch_team_stats("LES 2026 Spring")

    assert get_mock.call_count == 2


def test_missing_table_raises(mocker):
    mocker.patch(
        "app.services.golgg_service.httpx.get", return_value=_fake_response("<html><body>nada</body></html>")
    )

    with pytest.raises(GolGGError):
        fetch_team_stats()


def _teams():
    return [
        TeamStat(name="UCAM Esports", games=15, win_rate=86.7, kda=2.13, gpm=2157, fb_pct=66.7, towers_killed=8.9),
        TeamStat(name="Barca eSports", games=16, win_rate=56.3, kda=1.22, gpm=2012, fb_pct=62.5, towers_killed=7.5),
        TeamStat(name="UB Alma Mater", games=16, win_rate=18.8, kda=0.60, gpm=1850, fb_pct=37.5, towers_killed=4.0),
    ]


def _players(penta_kills=(0, 1, 0), solo_kills=(8, 3, 0)):
    return [
        PlayerStat(name="Escik", games=15, win_rate=86.7, kda=9.4, csm=9.2, avg_kills=6.7, penta_kills=penta_kills[0], solo_kills=solo_kills[0]),
        PlayerStat(name="XnS", games=16, win_rate=87.5, kda=7.1, csm=7.4, avg_kills=5.5, penta_kills=penta_kills[1], solo_kills=solo_kills[1]),
        PlayerStat(name="Hydra", games=16, win_rate=31.3, kda=2.5, csm=8.6, avg_kills=3.0, penta_kills=penta_kills[2], solo_kills=solo_kills[2]),
    ]


def test_compute_candidates_teams_and_players():
    candidates = compute_candidates(_teams(), _players(), {"teams", "players"})
    kinds = {c.kind for c in candidates}

    assert "team_kda" in kinds
    assert "team_winrate" in kinds
    assert "team_fb" in kinds
    assert "team_winrate_contrast" in kinds
    assert "player_kda" in kinds
    assert "player_csm" in kinds
    assert "player_solo_kills" in kinds
    assert "player_penta_kills" in kinds

    best_kda = next(c for c in candidates if c.kind == "team_kda")
    assert best_kda.subject == "UCAM Esports"
    best_player_kda = next(c for c in candidates if c.kind == "player_kda")
    assert best_player_kda.subject == "Escik"
    assert "9.4" in best_player_kda.fact_sentence


def test_compute_candidates_omits_penta_kills_when_all_zero():
    candidates = compute_candidates([], _players(penta_kills=(0, 0, 0)), {"players"})
    assert "player_penta_kills" not in {c.kind for c in candidates}


def test_compute_candidates_respects_categories_filter():
    candidates = compute_candidates(_teams(), _players(), {"players"})
    assert all(c.kind.startswith("player_") for c in candidates)


def test_pick_candidate_with_focus():
    candidates = compute_candidates(_teams(), _players(), {"teams", "players"})
    chosen = pick_candidate(candidates, focus="escik")
    assert chosen.subject == "Escik"


def test_pick_candidate_focus_not_found_raises():
    candidates = compute_candidates(_teams(), _players(), {"teams", "players"})
    with pytest.raises(StatFocusNotFoundError):
        pick_candidate(candidates, focus="nadie con este nombre")


def test_format_stat_tweet_plain_structure():
    candidates = compute_candidates(_teams(), _players(), {"players"})
    candidate = next(c for c in candidates if c.kind == "player_kda")
    text = format_stat_tweet_plain(candidate)

    lines = text.split("\n")
    assert len(lines) == 3
    assert lines[0] == f"{candidate.plano_emoji} {candidate.plano_title}"
    assert lines[1] == candidate.fact_sentence
    assert candidate.plano_question in lines[2]


def test_get_year_tournaments_parses_comma_separated(monkeypatch):
    import app.services.golgg_service as golgg_service

    monkeypatch.setattr(golgg_service.settings, "golgg_year_tournaments", "LES 2026 Spring, LES 2026 Summer")
    assert get_year_tournaments() == ["LES 2026 Spring", "LES 2026 Summer"]


def test_fetch_match_results_parses_by_fixed_index(mocker):
    html = _matchlist_html(
        [
            ("UCAM Esports", "2 - 0", "Barca eSports"),
            ("Movistar KOI Fenix", "2 - 1", "Team Heretics Academy"),
        ]
    )
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    results = fetch_match_results("LES 2026 Summer")

    assert len(results) == 2
    assert results[0].winner == "UCAM Esports"
    assert results[0].loser == "Barca eSports"
    assert results[0].winner_maps == 2
    assert results[0].loser_maps == 0
    assert results[0].date == "2026-01-01"
    assert results[0].tournament == "LES 2026 Summer"


def test_fetch_match_results_detects_winner_by_css_class_not_position(mocker):
    # Caso real detectado: gol.gg pone al ganador en la celda 3 a veces, no
    # siempre en la 1. Si se ignora la clase css "text_victory" y se asume
    # posicion fija, el resultado queda invertido.
    html = _matchlist_html([("UCAM Esports", "0 - 2", "Barca eSports")], winner_in_position_3=True)
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    results = fetch_match_results("LES 2026 Summer")

    assert len(results) == 1
    assert results[0].winner == "UCAM Esports"
    assert results[0].loser == "Barca eSports"


def test_fetch_match_results_skips_row_without_victory_class(mocker):
    html = (
        '<html><body><table class="table_list footable toggle-square-filled">'
        "<tr><th>Game</th><th></th><th>Score</th><th></th><th></th><th>Patch</th><th>Date</th></tr>"
        "<tr><td>X vs Y</td><td>Equipo A</td><td>1 - 1</td><td>Equipo B</td>"
        "<td>WEEK1</td><td>16.15</td><td>2026-01-01</td></tr>"
        "</table></body></html>"
    )
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    results = fetch_match_results("LES 2026 Summer")

    assert results == []


def test_compute_head_to_head_clear_leader(mocker):
    html = _matchlist_html(
        [
            ("UCAM Esports", "2 - 0", "Barca eSports"),
            ("UCAM Esports", "2 - 1", "Barca eSports"),
            ("Barca eSports", "2 - 0", "UCAM Esports"),
        ]
    )
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    candidates = compute_head_to_head_candidates(["LES 2026 Summer"])

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind == "team_head_to_head"
    assert "UCAM Esports" in candidate.subject and "Barca eSports" in candidate.subject
    assert "UCAM Esports le gano a Barca eSports en 2 de sus 3 cruces" in candidate.fact_sentence
    assert "mapas: 4-3" in candidate.fact_sentence


def test_compute_head_to_head_includes_total_maps_when_tied(mocker):
    html = _matchlist_html(
        [
            ("UCAM Esports", "2 - 0", "Barca eSports"),
            ("Barca eSports", "2 - 1", "UCAM Esports"),
        ]
    )
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    candidates = compute_head_to_head_candidates(["LES 2026 Summer"])

    assert len(candidates) == 1
    # UCAM: 2 (ganador partido1) + 1 (perdedor partido2) = 3. Barca: 0 + 2 = 2.
    # Orden alfabetico en la frase (team_a=Barca, team_b=UCAM) -> "mapas: 2-3".
    assert "mapas: 2-3" in candidates[0].fact_sentence


def test_compute_head_to_head_combines_multiple_tournaments(mocker):
    def fake_get(url, headers, timeout):
        if "Spring" in url:
            html = _matchlist_html([("UCAM Esports", "2 - 0", "Barca eSports")])
        else:
            html = _matchlist_html([("UCAM Esports", "2 - 1", "Barca eSports")])
        return _fake_response(html)

    mocker.patch("app.services.golgg_service.httpx.get", side_effect=fake_get)

    candidates = compute_head_to_head_candidates(["LES 2026 Spring", "LES 2026 Summer"])

    assert len(candidates) == 1
    assert "UCAM Esports le gano a Barca eSports en 2 de sus 2 cruces" in candidates[0].fact_sentence


def test_compute_head_to_head_tied_record(mocker):
    html = _matchlist_html(
        [
            ("UCAM Esports", "2 - 0", "Barca eSports"),
            ("Barca eSports", "2 - 1", "UCAM Esports"),
        ]
    )
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    candidates = compute_head_to_head_candidates(["LES 2026 Summer"])

    assert len(candidates) == 1
    assert "se repartieron sus 2 cruces" in candidates[0].fact_sentence


def test_aggregate_team_stats_weighted_average(mocker):
    # Mismo equipo, 10 partidos al 100% en un torneo y 10 partidos al 0% en otro -> 50%.
    def fake_get(url, headers, timeout):
        if "Spring" in url:
            rows = [["UCAM Esports", "S16", "ES", "10", "100%", "2.0", "2000", "0", "30:00", "20%", "50%", "20", "10", "8", "5", "70"]]
        else:
            rows = [["UCAM Esports", "S16", "ES", "10", "0%", "1.0", "1800", "0", "30:00", "20%", "50%", "10", "20", "4", "8", "40"]]
        return _fake_response(_teams_html(rows))

    mocker.patch("app.services.golgg_service.httpx.get", side_effect=fake_get)

    merged = aggregate_team_stats(["LES 2026 Spring", "LES 2026 Summer"])

    assert len(merged) == 1
    assert merged[0].games == 20
    assert merged[0].win_rate == 50.0


def test_aggregate_player_stats_sums_pentas_and_solo_kills(mocker):
    def fake_get(url, headers, timeout):
        if "Spring" in url:
            rows = [["Escik", "PL", "10", "80%", "5.0", "5.0", "1.0", "5.0", "9.0", "450", "60%", "25%", "22%", "12%", "700", "1.0", "0.4", "0.2", "0.1", "10", "1", "2", "10%", "5%", "1", "2"]]
        else:
            rows = [["Escik", "PL", "10", "90%", "9.4", "6.7", "1.8", "10.0", "9.2", "465", "60%", "25%", "22%", "12%", "800", "1.1", "0.4", "0.2", "0.1", "50", "5", "10", "18.8%", "12%", "0", "8"]]
        return _fake_response(_players_html(rows))

    mocker.patch("app.services.golgg_service.httpx.get", side_effect=fake_get)

    merged = aggregate_player_stats(["LES 2026 Spring", "LES 2026 Summer"])

    assert len(merged) == 1
    assert merged[0].games == 20
    assert merged[0].penta_kills == 1
    assert merged[0].solo_kills == 10


def test_find_head_to_head_matches_exact_pair(mocker):
    html = _matchlist_html(
        [
            ("UCAM Esports", "2 - 0", "Barca eSports"),
            ("Barca eSports", "2 - 1", "UB Alma Mater"),
        ]
    )
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    found = find_head_to_head("UCAM Esports", "Barca eSports", ["LES 2026 Summer"])

    assert found is not None
    assert found.kind == "team_head_to_head"
    assert "UCAM Esports" in found.subject and "Barca eSports" in found.subject


def test_find_head_to_head_is_case_insensitive_and_order_independent(mocker):
    html = _matchlist_html([("UCAM Esports", "2 - 0", "Barca eSports")])
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    found = find_head_to_head("barca esports", "ucam esports", ["LES 2026 Summer"])

    assert found is not None


def test_find_head_to_head_no_match_returns_none(mocker):
    html = _matchlist_html([("UCAM Esports", "2 - 0", "Barca eSports")])
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    found = find_head_to_head("UCAM Esports", "UB Alma Mater", ["LES 2026 Summer"])

    assert found is None


def test_get_team_handles_parses_name_handle_pairs(monkeypatch):
    import app.services.golgg_service as golgg_service

    monkeypatch.setattr(
        golgg_service.settings, "team_handles", "UCAM Esports:@UCAM_esports,Barca eSports:@FCBeSports"
    )
    assert get_team_handles() == {"UCAM Esports": "@UCAM_esports", "Barca eSports": "@FCBeSports"}


def _team_candidate(kind, subject):
    return StatCandidate(
        kind=kind,
        subject=subject,
        fact_sentence="algun dato real",
        plano_emoji="🔥",
        plano_title="TITULO",
        plano_question="¿pregunta?",
    )


def test_stat_closing_tags_single_team(monkeypatch):
    import app.services.golgg_service as golgg_service

    monkeypatch.setattr(golgg_service.settings, "team_handles", "UCAM Esports:@UCAM_esports")
    monkeypatch.setattr(golgg_service.settings, "league_handle_les", "@LESESPORTS")
    monkeypatch.setattr(golgg_service.settings, "custom_hashtags", "#LT")

    tags = stat_closing_tags(_team_candidate("team_kda", "UCAM Esports"))

    assert tags == "@UCAM_esports @LESESPORTS #LT"


def test_stat_closing_tags_head_to_head_both_teams(monkeypatch):
    import app.services.golgg_service as golgg_service

    monkeypatch.setattr(
        golgg_service.settings, "team_handles", "UCAM Esports:@UCAM_esports,Barca eSports:@FCBeSports"
    )
    monkeypatch.setattr(golgg_service.settings, "league_handle_les", "@LESESPORTS")
    monkeypatch.setattr(golgg_service.settings, "custom_hashtags", "#LT")

    tags = stat_closing_tags(_team_candidate("team_head_to_head", "Barca eSports vs UCAM Esports"))

    assert tags == "@FCBeSports @UCAM_esports @LESESPORTS #LT"


def test_stat_closing_tags_player_candidate_has_no_team_handle(monkeypatch):
    import app.services.golgg_service as golgg_service

    monkeypatch.setattr(golgg_service.settings, "team_handles", "UCAM Esports:@UCAM_esports")
    monkeypatch.setattr(golgg_service.settings, "league_handle_les", "@LESESPORTS")
    monkeypatch.setattr(golgg_service.settings, "custom_hashtags", "#LT")

    tags = stat_closing_tags(_team_candidate("player_kda", "Escik"))

    assert tags == "@LESESPORTS #LT"


def test_stat_closing_tags_unknown_team_has_no_handle(monkeypatch):
    import app.services.golgg_service as golgg_service

    monkeypatch.setattr(golgg_service.settings, "team_handles", "")
    monkeypatch.setattr(golgg_service.settings, "league_handle_les", "@LESESPORTS")
    monkeypatch.setattr(golgg_service.settings, "custom_hashtags", "#LT")

    tags = stat_closing_tags(_team_candidate("team_kda", "Un equipo sin handle cargado"))

    assert tags == "@LESESPORTS #LT"


def _result(winner, loser, date, winner_maps=2, loser_maps=0, tournament="LES 2026 Summer"):
    return MatchResult(
        winner=winner, loser=loser, winner_maps=winner_maps, loser_maps=loser_maps, date=date, tournament=tournament
    )


def test_recent_form_last_n_games_most_recent_first():
    results = [
        _result("UCAM Esports", "Barca eSports", "2026-01-01"),
        _result("Barca eSports", "UCAM Esports", "2026-02-01"),
        _result("UCAM Esports", "GX", "2026-03-01"),
        _result("UCAM Esports", "LUA", "2026-04-01"),
        _result("Falke", "UCAM Esports", "2026-05-01"),
        _result("UCAM Esports", "Heretics", "2026-06-01"),  # 6to partido, no deberia contar con n=5
    ]

    form = _recent_form("UCAM Esports", results, n=5)

    assert form.games == 5
    # Los 5 mas recientes (feb..jun): gano feb? no, perdio feb (Barca gano);
    # gano mar, gano abr, perdio may (Falke gano), gano jun -> 3V-2D
    assert form.wins == 3
    assert form.losses == 2


def test_recent_form_fewer_than_n_games():
    results = [_result("UCAM Esports", "Barca eSports", "2026-01-01")]
    form = _recent_form("UCAM Esports", results, n=5)
    assert form.games == 1
    assert form.wins == 1


def test_recent_form_no_games_returns_none():
    results = [_result("Barca eSports", "GX", "2026-01-01")]
    assert _recent_form("UCAM Esports", results, n=5) is None


def test_build_head_to_head_preview_normal_case(mocker):
    html = _matchlist_html(
        [
            ("UCAM Esports", "2 - 0", "Barca eSports", "2026-01-01"),
            ("Barca eSports", "2 - 1", "UCAM Esports", "2026-06-01"),
        ]
    )
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    preview = build_head_to_head_preview("UCAM Esports", "Barca eSports", ["LES 2026 Summer"])

    assert preview.total_wins_a == 1
    assert preview.total_wins_b == 1
    assert preview.total_maps_a == 2 + 1  # gano 2-0, perdio 1-2
    assert preview.total_maps_b == 0 + 2
    assert preview.last_meeting.date == "2026-06-01"
    assert preview.last_meeting.winner == "Barca eSports"
    assert preview.last_win_by_a.date == "2026-01-01"
    assert preview.last_win_by_b.date == "2026-06-01"
    assert preview.recent_form_a.games == 2
    assert preview.recent_form_b.games == 2


def test_build_head_to_head_preview_no_prior_meetings(mocker):
    html = _matchlist_html([("UCAM Esports", "2 - 0", "GX", "2026-01-01")])
    mocker.patch("app.services.golgg_service.httpx.get", return_value=_fake_response(html))

    preview = build_head_to_head_preview("UCAM Esports", "Barca eSports", ["LES 2026 Summer"])

    assert preview.total_wins_a == 0
    assert preview.total_wins_b == 0
    assert preview.last_meeting is None
    assert preview.last_win_by_a is None
    assert preview.last_win_by_b is None
    assert preview.recent_form_a.games == 1  # UCAM jugo contra GX
    assert preview.recent_form_b is None  # Barca no aparece en ningun resultado






def test_fetch_all_match_results_combines_tournaments(mocker):
    def fake_get(url, headers, timeout):
        if "Spring" in url:
            html = _matchlist_html([("UCAM Esports", "2 - 0", "Barca eSports", "2026-01-01")])
        else:
            html = _matchlist_html([("Barca eSports", "2 - 1", "UCAM Esports", "2026-06-01")])
        return _fake_response(html)

    mocker.patch("app.services.golgg_service.httpx.get", side_effect=fake_get)

    results = fetch_all_match_results(["LES 2026 Spring", "LES 2026 Summer"])

    assert len(results) == 2
    assert {r.tournament for r in results} == {"LES 2026 Spring", "LES 2026 Summer"}


def _full_preview():
    import app.services.golgg_service as golgg_service

    return golgg_service.HeadToHeadPreviewData(
        team_a="UCAM Esports",
        team_b="Barca eSports",
        total_wins_a=1,
        total_wins_b=3,
        total_maps_a=5,
        total_maps_b=6,
        last_meeting=_result("Barca eSports", "UCAM Esports", "2026-08-20", tournament="LES 2026 Summer Playoffs"),
        last_win_by_a=_result("UCAM Esports", "Barca eSports", "2026-07-22"),
        last_win_by_b=_result("Barca eSports", "UCAM Esports", "2026-08-20", tournament="LES 2026 Summer Playoffs"),
        recent_form_a=golgg_service.RecentForm(wins=2, losses=3, games=5),
        recent_form_b=golgg_service.RecentForm(wins=4, losses=1, games=5),
    )


def _empty_preview():
    import app.services.golgg_service as golgg_service

    return golgg_service.HeadToHeadPreviewData(
        team_a="UCAM Esports",
        team_b="GX",
        total_wins_a=0,
        total_wins_b=0,
        total_maps_a=0,
        total_maps_b=0,
        last_meeting=None,
        last_win_by_a=None,
        last_win_by_b=None,
        recent_form_a=None,
        recent_form_b=None,
    )


def test_format_h2h_variant_plain_historial_with_data():
    text = format_h2h_variant_plain(_full_preview(), "historial")

    assert "UCAM Esports 🆚 Barca eSports" in text
    assert "UCAM Esports 1-3 Barca eSports (mapas: 5-6)" in text
    assert "El ultimo cruce (2026-08-20) lo gano Barca eSports." in text
    assert "¿Se repite la historia hoy? 👀" in text


def test_format_h2h_variant_plain_forma_reciente_with_data():
    text = format_h2h_variant_plain(_full_preview(), "forma_reciente")

    assert "UCAM Esports 2V-3D" in text
    assert "Barca eSports 4V-1D" in text
    assert "manda Barca eSports (1-3)" in text
    assert "¿Quien llega mejor hoy? 👀" in text


def test_format_h2h_variant_plain_no_data_never_invents():
    historial = format_h2h_variant_plain(_empty_preview(), "historial")
    forma = format_h2h_variant_plain(_empty_preview(), "forma_reciente")

    assert "Primer cruce del año entre UCAM Esports y GX esta temporada." in historial
    assert "Todavia no hay antecedentes directos esta temporada." in historial
    assert "sin datos recientes" in forma
    assert "Sin cruces previos esta temporada para comparar." in forma


def test_format_h2h_variant_plain_includes_today_context():
    text = format_h2h_variant_plain(
        _full_preview(), "historial", today_context="Partido de hoy: fase 'Final', horario 17:00 (Madrid)."
    )
    assert "Partido de hoy: fase 'Final', horario 17:00 (Madrid)." in text


def test_get_lec_tournament_reads_setting(monkeypatch):
    import app.services.golgg_service as golgg_service

    monkeypatch.setattr(golgg_service.settings, "lec_tournament", "LEC 2026 Summer Season")
    assert get_lec_tournament() == "LEC 2026 Summer Season"


def _les_teams():
    return [
        TeamStat(name="UCAM Esports", games=15, win_rate=86.7, kda=2.13, gpm=2157, fb_pct=66.7, towers_killed=8.9),
        TeamStat(name="Barca eSports", games=16, win_rate=56.3, kda=1.22, gpm=2012, fb_pct=62.5, towers_killed=7.5),
    ]


def _lec_teams():
    return [
        TeamStat(name="Fnatic", games=20, win_rate=50.0, kda=1.5, gpm=2100, fb_pct=55.0, towers_killed=8.0),
        TeamStat(name="G2 Esports", games=20, win_rate=60.0, kda=1.7, gpm=2200, fb_pct=60.0, towers_killed=8.5),
    ]


def _les_players():
    return [
        PlayerStat(name="Escik", games=15, win_rate=86.7, kda=9.4, csm=9.2, avg_kills=6.7, penta_kills=0, solo_kills=8),
    ]


def _lec_players():
    return [
        PlayerStat(name="Caps", games=20, win_rate=55.0, kda=4.0, csm=9.5, avg_kills=4.5, penta_kills=0, solo_kills=2),
        PlayerStat(name="Rekkles", games=20, win_rate=45.0, kda=3.0, csm=9.0, avg_kills=3.5, penta_kills=0, solo_kills=1),
    ]


def test_compute_league_comparison_candidates_covers_team_and_player_kinds():
    candidates = compute_league_comparison_candidates(_les_teams(), _les_players(), _lec_teams(), _lec_players())
    kinds = {c.kind for c in candidates}

    assert kinds == {"team_kda", "team_winrate", "team_fb", "player_kda"}

    team_kda = next(c for c in candidates if c.kind == "team_kda")
    assert team_kda.subject == "UCAM Esports"
    assert "2.13" in team_kda.fact_sentence
    assert "1.6" in team_kda.fact_sentence  # promedio LEC (1.5+1.7)/2 = 1.6
    assert "nivel y muestra distintos" in team_kda.nuance

    player_kda = next(c for c in candidates if c.kind == "player_kda")
    assert player_kda.subject == "Escik"
    assert "9.4" in player_kda.fact_sentence
    assert "3.5" in player_kda.fact_sentence  # promedio LEC (4.0+3.0)/2 = 3.5
    assert "inflado" in player_kda.nuance


def test_compute_league_comparison_candidates_empty_without_both_sides():
    only_les = compute_league_comparison_candidates(_les_teams(), [], [], [])
    assert only_les == []

    only_teams_no_players = compute_league_comparison_candidates(_les_teams(), [], _lec_teams(), [])
    assert {c.kind for c in only_teams_no_players} == {"team_kda", "team_winrate", "team_fb"}


def test_pick_league_comparison_candidate_with_focus():
    candidates = compute_league_comparison_candidates(_les_teams(), _les_players(), _lec_teams(), _lec_players())
    chosen = pick_league_comparison_candidate(candidates, focus="Escik")
    assert chosen.subject == "Escik"


def test_pick_league_comparison_candidate_focus_not_found_raises():
    candidates = compute_league_comparison_candidates(_les_teams(), _les_players(), _lec_teams(), _lec_players())
    with pytest.raises(StatFocusNotFoundError):
        pick_league_comparison_candidate(candidates, focus="nadie con este nombre")


def test_pick_league_comparison_candidate_empty_pool_raises():
    with pytest.raises(GolGGError):
        pick_league_comparison_candidate([])


def test_format_league_comparison_plain_sorprendente_and_debate_tones():
    candidates = compute_league_comparison_candidates(_les_teams(), _les_players(), _lec_teams(), _lec_players())
    candidate = next(c for c in candidates if c.kind == "team_kda")

    sorprendente = format_league_comparison_plain(candidate, "sorprendente")
    debate = format_league_comparison_plain(candidate, "debate")

    assert "DATO LES-LEC" in sorprendente
    assert candidate.fact_sentence in sorprendente
    assert candidate.nuance in sorprendente

    assert "DEBATE LES-LEC" in debate
    assert candidate.fact_sentence in debate
    assert candidate.nuance in debate
    assert sorprendente != debate
