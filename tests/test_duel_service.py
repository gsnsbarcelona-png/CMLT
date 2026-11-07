from app.services.duel_service import (
    _pick_starter,
    compute_duel_candidates,
    reconcile_player_casing,
)
from app.services.golgg_service import PlayerStat
from app.services.lolesports_service import RosterPlayer


def _player_stat(name, games=15, kda=3.0):
    return PlayerStat(
        name=name, games=games, win_rate=50.0, kda=kda, csm=8.0, avg_kills=3.0, penta_kills=0, solo_kills=1
    )


def test_reconcile_player_casing_uses_known_capitalization():
    known = ["Escik", "Andariel"]
    assert reconcile_player_casing(["ESCIK", "andariel"], known) == ["Escik", "Andariel"]


def test_reconcile_player_casing_falls_back_to_original_when_no_match():
    assert reconcile_player_casing(["Nadie"], ["Escik"]) == ["Nadie"]


def test_pick_starter_returns_none_when_no_stats():
    players = [RosterPlayer(name="Nadie", role="mid")]
    assert _pick_starter(players, {}) is None


def test_pick_starter_picks_most_games_among_candidates():
    players = [RosterPlayer(name="Sub", role="mid"), RosterPlayer(name="Titular", role="mid")]
    stats_by_name = {
        "sub": _player_stat("Sub", games=3),
        "titular": _player_stat("Titular", games=20),
    }

    picked = _pick_starter(players, stats_by_name)

    assert picked[0].name == "Titular"


def test_pick_starter_ignores_players_without_stats():
    players = [RosterPlayer(name="SinDatos", role="mid"), RosterPlayer(name="ConDatos", role="mid")]
    stats_by_name = {"condatos": _player_stat("ConDatos", games=5)}

    picked = _pick_starter(players, stats_by_name)

    assert picked[0].name == "ConDatos"


def test_compute_duel_candidates_matches_common_roles():
    roster_a = [RosterPlayer(name="Escik", role="mid"), RosterPlayer(name="Andariel", role="bottom")]
    roster_b = [RosterPlayer(name="Fulano", role="mid")]
    player_stats = [_player_stat("Escik", kda=9.4), _player_stat("Fulano", kda=4.0)]

    candidates = compute_duel_candidates(roster_a, roster_b, player_stats)

    assert len(candidates) == 1
    assert candidates[0].kind == "individual_duel"
    assert candidates[0].subject == "Escik vs Fulano"
    assert candidates[0].title == "DUELO DE MID"
    assert candidates[0].hook == "MID: Escik (9.4 de KDA) vs Fulano (4): Escik le saca 5.4 a Fulano"
    assert "partidos" in candidates[0].fact_sentence


def test_duel_hook_tie_and_second_player_ahead():
    roster_a = [RosterPlayer(name="A", role="top")]
    roster_b = [RosterPlayer(name="B", role="top")]
    tie = compute_duel_candidates(roster_a, roster_b, [_player_stat("A", kda=3.0), _player_stat("B", kda=3.0)])
    assert tie[0].hook.endswith("igualados") and "saca" not in tie[0].hook
    behind = compute_duel_candidates(roster_a, roster_b, [_player_stat("A", kda=2.0), _player_stat("B", kda=3.5)])
    assert behind[0].hook.endswith("B le saca 1.5 a A")


def test_compute_duel_candidates_skips_role_without_stats_on_one_side():
    roster_a = [RosterPlayer(name="Escik", role="mid")]
    roster_b = [RosterPlayer(name="SinDatos", role="mid")]
    player_stats = [_player_stat("Escik")]

    candidates = compute_duel_candidates(roster_a, roster_b, player_stats)

    assert candidates == []


def test_compute_duel_candidates_skips_role_missing_from_one_team():
    roster_a = [RosterPlayer(name="Escik", role="mid")]
    roster_b = [RosterPlayer(name="Fulano", role="top")]
    player_stats = [_player_stat("Escik"), _player_stat("Fulano")]

    candidates = compute_duel_candidates(roster_a, roster_b, player_stats)

    assert candidates == []


def test_compute_duel_candidates_ignores_players_without_role():
    roster_a = [RosterPlayer(name="Escik", role="")]
    roster_b = [RosterPlayer(name="Fulano", role="")]
    player_stats = [_player_stat("Escik"), _player_stat("Fulano")]

    assert compute_duel_candidates(roster_a, roster_b, player_stats) == []


def test_compute_duel_candidates_multiple_roles():
    roster_a = [RosterPlayer(name="Escik", role="mid"), RosterPlayer(name="Andariel", role="bottom")]
    roster_b = [RosterPlayer(name="Fulano", role="mid"), RosterPlayer(name="Mengano", role="bottom")]
    player_stats = [
        _player_stat("Escik"),
        _player_stat("Fulano"),
        _player_stat("Andariel"),
        _player_stat("Mengano"),
    ]

    candidates = compute_duel_candidates(roster_a, roster_b, player_stats)

    assert {c.title for c in candidates} == {"DUELO DE MID", "DUELO DE ADC"}
