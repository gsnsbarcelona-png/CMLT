"""Tests de contrato del scraping de gol.gg.

Parsean HTML real guardado en tests/fixtures (sin red) para detectar cambios de
estructura. El test marcado `live` descarga la pagina real y comprueba que las
cabeceras esperadas siguen existiendo (no se ejecuta por defecto).
"""
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup

from app.services import golgg_service as g

FIXTURES = Path(__file__).parent / "fixtures"
TOURNAMENT = "LES 2026 Summer"

TEAM_HEADERS = ["Name", "Games", "Win rate", "K:D", "GPM", "FB%", "Towers killed", "DRAPG", "Game duration"]
PLAYER_HEADERS = ["Player", "Games", "Win rate", "KDA", "CSM", "Avg kills", "Penta Kills", "Solo Kills"]


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def patch_html(monkeypatch):
    def _patch(name: str):
        html = _fixture(name)
        monkeypatch.setattr(g, "_cached_get", lambda url: html)
    return _patch


def test_team_stats_contract(patch_html):
    patch_html("golgg_teams.html")
    teams = g.fetch_team_stats(TOURNAMENT)
    assert len(teams) > 3
    for t in teams:
        assert t.name.strip()
        assert t.games > 0
        assert 0 <= t.win_rate <= 100
        assert t.kda > 0
        assert t.gpm > 0
        assert 0 <= t.fb_pct <= 100
        assert t.towers_killed >= 0
        assert t.dragons_per_game >= 0
        assert 600 < t.avg_game_duration_seconds < 7200


def test_player_stats_contract(patch_html):
    patch_html("golgg_players.html")
    players = g.fetch_player_stats(TOURNAMENT)
    assert len(players) > 3
    for p in players:
        assert p.name.strip()
        assert p.games > 0
        assert 0 <= p.win_rate <= 100
        assert p.kda > 0
        assert p.csm >= 0
        assert p.avg_kills >= 0
        assert p.penta_kills >= 0
        assert p.solo_kills >= 0


def test_match_results_contract(patch_html):
    patch_html("golgg_matchlist.html")
    results = g.fetch_match_results(TOURNAMENT)
    assert len(results) > 3
    for r in results:
        assert r.winner.strip() and r.loser.strip()
        assert r.winner != r.loser
        assert r.winner_maps > r.loser_maps >= 0
        assert r.date
    assert any(r.date[:4].isdigit() for r in results)


def test_tournament_path_format():
    url = g._tournament_path("teams", TOURNAMENT)
    assert url.startswith("https://gol.gg/teams/list/season-")
    assert f"split-ALL/tournament-{TOURNAMENT}/" in url


@pytest.mark.live
@pytest.mark.parametrize(
    "prefix,expected",
    [("teams", TEAM_HEADERS), ("players", PLAYER_HEADERS)],
)
def test_live_headers_still_present(prefix, expected):
    url = g._tournament_path(prefix, TOURNAMENT)
    response = httpx.get(url, headers=g.GOLGG_HEADERS, timeout=20.0, follow_redirects=True)
    assert response.status_code == 200
    table = BeautifulSoup(response.text, "html.parser").find("table", class_="playerslist")
    assert table is not None, "gol.gg ya no devuelve <table class='playerslist'>"
    headers = [c.get_text(strip=True) for c in table.find_all("tr")[0].find_all(["th", "td"])]
    missing = [h for h in expected if h not in headers]
    assert not missing, f"Cabeceras desaparecidas en gol.gg: {missing}"
