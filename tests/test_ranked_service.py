import httpx

import pytest

from app.services.ranked_service import (
    PlayerRank,
    RankedError,
    _parse_rank_block,
    _slugify,
    compute_player_vs_player_candidate,
    compute_rank_candidates,
    compute_team_vs_team_candidate,
    fetch_all_player_ranks,
    fetch_player_rank,
)


def _rank_block_html(current: dict | None, peak: dict | None) -> str:
    def block(section_id: str, data: dict | None) -> str:
        if data is None:
            return f'<div id="{section_id}"></div>'
        return f"""
        <div id="{section_id}">
          <div class="card rank-display">
            <p class="rank">{data["tier"]}</p>
            <p class="league-points">{data["lp"]} LP</p>
            <p class="games">
              <span class="wins">{data["wins"]}</span>/<span class="losses">{data["losses"]}</span>
            </p>
            <time title="{data["date"]}">{data["date"]}</time>
          </div>
        </div>
        """

    return f"<html><body>{block('current-elo', current)}{block('peak-elo', peak)}</body></html>"


CURRENT = {"tier": "Challenger", "lp": 2698, "wins": 281, "losses": 189, "date": "28/08"}
PEAK = {"tier": "Challenger", "lp": 2813, "wins": 280, "losses": 185, "date": "16/08"}


def _fake_response(text: str = "", status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://lolpros.gg/player/x")
    return httpx.Response(status_code=status_code, request=request, text=text)


def test_slugify():
    assert _slugify("Escik") == "escik"
    assert _slugify("  Th3Antonio  ") == "th3antonio"


def test_slugify_applies_known_overrides():
    # Casos reales donde el nombre de gol.gg no coincide con el slug real de
    # lolpros.gg -- verificados a mano (ver KNOWN_SLUG_OVERRIDES).
    assert _slugify("Macaquinho") == "macaquino"
    assert _slugify("Kaii1") == "kaii"
    assert _slugify("mercy9") == "mercy"
    assert _slugify("KoIdo") == "koldo"


def test_parse_rank_block_full():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_rank_block_html(CURRENT, PEAK), "html.parser")
    parsed = _parse_rank_block(soup, "current-elo")
    assert parsed == CURRENT


def test_parse_rank_block_missing_section_returns_none():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert _parse_rank_block(soup, "current-elo") is None


def test_parse_rank_block_empty_section_returns_none():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_rank_block_html(None, None), "html.parser")
    assert _parse_rank_block(soup, "current-elo") is None


def test_fetch_player_rank_success(mocker):
    mocker.patch(
        "app.services.ranked_service.httpx.get",
        return_value=_fake_response(_rank_block_html(CURRENT, PEAK)),
    )

    rank = fetch_player_rank("Escik")

    assert rank is not None
    assert rank.player == "Escik"
    assert rank.slug == "escik"
    assert rank.tier == "Challenger"
    assert rank.lp == 2698
    assert rank.wins == 281
    assert rank.losses == 189
    assert rank.peak_tier == "Challenger"
    assert rank.peak_lp == 2813
    assert rank.winrate == round(100 * 281 / (281 + 189), 1)


def test_fetch_player_rank_no_peak_block(mocker):
    mocker.patch(
        "app.services.ranked_service.httpx.get",
        return_value=_fake_response(_rank_block_html(CURRENT, None)),
    )

    rank = fetch_player_rank("Escik")

    assert rank is not None
    assert rank.peak_tier is None
    assert rank.peak_lp is None


def test_fetch_player_rank_404_returns_none(mocker):
    mocker.patch(
        "app.services.ranked_service.httpx.get", return_value=_fake_response("not found", status_code=404)
    )

    assert fetch_player_rank("NoExiste") is None


def test_fetch_player_rank_500_returns_none(mocker):
    # Confirmado en vivo: lolpros.gg devuelve 500 (no 404) para algunos
    # slugs de jugador que no existen -- se trata igual que "no encontrado".
    mocker.patch(
        "app.services.ranked_service.httpx.get", return_value=_fake_response("error", status_code=500)
    )

    assert fetch_player_rank("Kaii1") is None


def test_fetch_player_rank_no_current_block_returns_none(mocker):
    mocker.patch(
        "app.services.ranked_service.httpx.get",
        return_value=_fake_response("<html><body>sin datos</body></html>"),
    )

    assert fetch_player_rank("Alguien") is None


def test_fetch_player_rank_network_error_raises(mocker):
    mocker.patch("app.services.ranked_service.httpx.get", side_effect=httpx.ConnectError("boom"))

    try:
        fetch_player_rank("Escik")
        assert False, "deberia haber tirado RankedError"
    except RankedError:
        pass


def test_fetch_player_rank_caches_second_call(mocker):
    get_mock = mocker.patch(
        "app.services.ranked_service.httpx.get",
        return_value=_fake_response(_rank_block_html(CURRENT, PEAK)),
    )

    fetch_player_rank("Escik")
    fetch_player_rank("Escik")

    get_mock.assert_called_once()


def test_fetch_all_player_ranks_mixed_resolution(mocker):
    def fake_fetch(name: str):
        if name == "Escik":
            return PlayerRank(player="Escik", slug="escik", **CURRENT)
        return None

    mocker.patch("app.services.ranked_service.fetch_player_rank", side_effect=fake_fetch)

    resolved, unresolved = fetch_all_player_ranks(["Escik", "Fantasma", "Escik"])

    assert [r.player for r in resolved] == ["Escik"]
    assert unresolved == ["Fantasma"]


def test_fetch_all_player_ranks_survives_per_player_network_error(mocker):
    def fake_fetch(name: str):
        if name == "Escik":
            raise RankedError("boom")
        return PlayerRank(player=name, slug=name.lower(), **CURRENT)

    mocker.patch("app.services.ranked_service.fetch_player_rank", side_effect=fake_fetch)

    resolved, unresolved = fetch_all_player_ranks(["Escik", "Andariel"])

    assert unresolved == ["Escik"]
    assert [r.player for r in resolved] == ["Andariel"]


def test_fetch_all_player_ranks_empty_input():
    resolved, unresolved = fetch_all_player_ranks([])
    assert resolved == []
    assert unresolved == []


def _rank(player: str, tier: str, lp: int, peak_tier: str | None = None, peak_lp: int | None = None) -> PlayerRank:
    return PlayerRank(
        player=player, slug=player.lower(), tier=tier, lp=lp, wins=10, losses=5, date="01/01",
        peak_tier=peak_tier, peak_lp=peak_lp, peak_wins=12, peak_losses=4, peak_date="01/06",
    )


def test_compute_rank_candidates_one_per_player():
    ranks = [_rank("Escik", "Challenger", 2698), _rank("Andariel", "Grandmaster", 900)]

    candidates = compute_rank_candidates(ranks)

    current_subjects = {c.subject for c in candidates if c.kind == "player_rank_current"}
    assert current_subjects == {"Escik", "Andariel"}


def test_compute_rank_candidates_leader_is_highest_tier():
    ranks = [_rank("Escik", "Challenger", 2698), _rank("Andariel", "Grandmaster", 900)]

    candidates = compute_rank_candidates(ranks)

    leader = [c for c in candidates if c.kind == "player_rank_leader"]
    assert len(leader) == 1
    assert leader[0].subject == "Escik"


def test_compute_rank_candidates_leader_handles_grand_master_with_space():
    # Regresion real: lolpros.gg devuelve "Grand Master" (con espacio) para
    # ese tier, no "Grandmaster" -- un parseo ingenuo (tomar solo la primera
    # palabra) lo dejaba sin matchear, por debajo incluso de Iron, y el
    # "mejor" terminaba siendo alguien en Master con mucho menos LP.
    ranks = [_rank("Selenex", "Grand Master", 2268), _rank("Pauporter", "Master", 41)]

    candidates = compute_rank_candidates(ranks)

    leader = [c for c in candidates if c.kind == "player_rank_leader"]
    assert leader[0].subject == "Selenex"


def test_compute_rank_candidates_leader_prefers_lower_division_same_tier():
    # "Diamond 1" (division mas alta dentro del tier) debe rankear por
    # encima de "Diamond 4", independientemente del LP crudo (el LP se
    # resetea por division, no es comparable entre divisiones distintas).
    ranks = [_rank("Legolas", "Diamond 4", 90), _rank("Otro", "Diamond 1", 10)]

    candidates = compute_rank_candidates(ranks)

    leader = [c for c in candidates if c.kind == "player_rank_leader"]
    assert leader[0].subject == "Otro"


def test_compute_rank_candidates_peak_drop_included_when_tier_differs():
    ranks = [_rank("Escik", "Grandmaster", 900, peak_tier="Challenger", peak_lp=2800)]

    candidates = compute_rank_candidates(ranks)

    assert any(c.kind == "player_rank_peak_drop" and c.subject == "Escik" for c in candidates)


def test_compute_rank_candidates_no_peak_drop_when_at_peak():
    ranks = [_rank("Escik", "Challenger", 2698, peak_tier="Challenger", peak_lp=2698)]

    candidates = compute_rank_candidates(ranks)

    assert not any(c.kind == "player_rank_peak_drop" for c in candidates)


def test_compute_rank_candidates_empty_input():
    assert compute_rank_candidates([]) == []


def test_compute_player_vs_player_candidate_identifies_higher():
    candidate = compute_player_vs_player_candidate(
        _rank("Escik", "Challenger", 2698), _rank("Andariel", "Grandmaster", 900)
    )

    assert candidate.kind == "player_rank_vs_player"
    assert candidate.subject == "Escik vs Andariel"
    assert candidate.hook == "Escik (Challenger, 2698 LP) vs Andariel (Grandmaster, 900 LP) en SoloQ"
    assert "Va arriba Escik" in candidate.fact_sentence


def test_player_vs_player_same_tier_gives_lp_gap_and_tie():
    gap = compute_player_vs_player_candidate(_rank("A", "Diamond 2", 80), _rank("B", "Diamond 2", 30))
    assert gap.fact_sentence == "Va arriba A, por 50 LP."
    tie = compute_player_vs_player_candidate(_rank("A", "Gold 1", 30), _rank("B", "Gold 1", 30))
    assert "igualados" in tie.fact_sentence and "por" not in tie.fact_sentence


def test_compute_team_vs_team_candidate_picks_best_of_each_side():
    ranks_a = [_rank("Escik", "Challenger", 2698), _rank("Kozi", "Gold", 20)]
    ranks_b = [_rank("Andariel", "Grandmaster", 900)]

    candidate = compute_team_vs_team_candidate("UCAM Esports", "Barca eSports", ranks_a, ranks_b)

    assert candidate.kind == "team_rank_vs_team"
    assert candidate.subject == "UCAM Esports vs Barca eSports"
    assert "Escik" in candidate.hook and "Andariel" in candidate.hook
    assert "Kozi" not in candidate.hook + candidate.fact_sentence
    assert "UCAM Esports" in candidate.hook and "2698 LP" in candidate.hook


def test_compute_team_vs_team_candidate_grand_master_beats_low_lp_master():
    # Caso real reportado: un roster con alguien en "Grand Master" (con
    # espacio) de verdad mas alto y otro apenas en Master con poco LP -- el
    # de Grand Master tiene que ganar, no el de menos elo real.
    ranks_a = [_rank("Selenex", "Grand Master", 2268), _rank("Pauporter", "Master", 41)]
    ranks_b = [_rank("Andariel", "Master", 900)]

    candidate = compute_team_vs_team_candidate("Barca eSports", "UCAM Esports", ranks_a, ranks_b)

    assert "Selenex" in candidate.fact_sentence
    assert "Pauporter" not in candidate.fact_sentence


def test_compute_team_vs_team_candidate_raises_when_a_side_has_no_ranks():
    with pytest.raises(RankedError):
        compute_team_vs_team_candidate("UCAM Esports", "Barca eSports", [], [_rank("Andariel", "Gold", 20)])

    with pytest.raises(RankedError):
        compute_team_vs_team_candidate("UCAM Esports", "Barca eSports", [_rank("Escik", "Gold", 20)], [])
