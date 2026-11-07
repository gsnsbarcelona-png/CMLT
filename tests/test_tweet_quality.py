"""Calidad de los tweets: gancho con dato+sujeto, comparaciones solo con datos
reales, racha en resultados y limite de 280 caracteres."""
from datetime import datetime, timezone

from app.services import char_count, lolesports_service, phrasing
from app.services.golgg_service import (
    PlayerStat,
    TeamStat,
    compute_candidates,
    compute_top_ranking_candidate,
    format_stat_tweet_plain,
    format_top_ranking_plain,
)

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


def _player(name, kda, games=15):
    return PlayerStat(name=name, games=games, win_rate=50, kda=kda, csm=8, avg_kills=3, penta_kills=0, solo_kills=0)


def _team(name, win_rate):
    return TeamStat(
        name=name, games=10, win_rate=win_rate, kda=1.5, gpm=2000, fb_pct=50, towers_killed=6,
        dragons_per_game=2, avg_game_duration_seconds=1900,
    )


# ------------------------------------------------------------------ stats
def test_stat_hook_has_subject_and_number_and_comparison():
    players = [_player("Escik", 9.4), _player("XnS", 5.0), _player("Hydra", 2.5)]
    candidate = next(c for c in compute_candidates([], players, {"players"}) if c.kind == "player_kda")
    lines = format_stat_tweet_plain(candidate).splitlines()

    assert lines[0] == "🔥 Escik lleva 9.4 de KDA: nadie en la liga se le acerca"
    assert "Media de la liga: 5.63" in lines[1] and "el segundo, XnS, 5" in lines[1]


def test_stat_without_rivals_omits_comparison_and_bold_claim():
    candidate = next(c for c in compute_candidates([], [_player("Escik", 9.4)], {"players"}) if c.kind == "player_kda")
    text = format_stat_tweet_plain(candidate)

    assert "Media de la liga" not in text and "segundo" not in text
    assert "nadie" not in text.splitlines()[0]
    assert text.splitlines()[0] == "🔥 Escik lidera el KDA de la liga con 9.4"


def test_close_race_does_not_claim_nobody_is_close():
    players = [_player("Escik", 9.4), _player("XnS", 9.0)]
    candidate = next(c for c in compute_candidates([], players, {"players"}) if c.kind == "player_kda")
    assert "nadie" not in candidate.hook


def test_pentakill_singular():
    p = PlayerStat(name="Hydra", games=10, win_rate=50, kda=2, csm=8, avg_kills=3, penta_kills=1, solo_kills=0)
    candidate = next(c for c in compute_candidates([], [p], {"players"}) if c.kind == "player_penta_kills")
    assert "1 pentakill " in candidate.hook and "pentakill(s)" not in candidate.fact_sentence


def test_hook_varies_when_variety_enabled(monkeypatch):
    monkeypatch.setattr(phrasing, "VARIETY_ENABLED", True)
    players = [_player("Escik", 9.4), _player("XnS", 5.0)]
    hooks = set()
    for _ in range(30):
        phrasing.reset_recent()
        hooks.add(next(c for c in compute_candidates([], players, {"players"}) if c.kind == "player_kda").hook)
    assert len(hooks) == 2 and all("Escik" in h and "9.4" in h for h in hooks)


def test_top_ranking_hook_and_media():
    players = [_player("Escik", 9.4), _player("XnS", 7.1), _player("Hydra", 2.5)]
    candidate = compute_top_ranking_candidate("player_kda", [], players)
    top3 = format_top_ranking_plain(candidate, "top3")

    assert top3.splitlines()[0] == "🔥 Escik lleva 9.4 de KDA: 2.3 más que XnS, el segundo"
    assert "Media de la liga: 6.33 de KDA." in top3


def test_top_ranking_single_entry_has_no_second():
    candidate = compute_top_ranking_candidate("player_kda", [], [_player("Escik", 9.4)])
    text = format_top_ranking_plain(candidate, "top1")
    assert "segundo" not in text and "el mejor de 1 con datos" in text


# -------------------------------------------------------------- resultados
def _event(start, s1, s2, codes, block="Jornada 1"):
    return {
        "startTime": start, "state": "completed", "type": "match", "blockName": block,
        "match": {"teams": [
            {"name": codes[0], "code": codes[0], "result": {"gameWins": s1}},
            {"name": codes[1], "code": codes[1], "result": {"gameWins": s2}},
        ]},
    }


def test_winner_streak_counts_previous_series(monkeypatch):
    events = [
        _event("2026-10-20T18:00:00Z", 2, 0, ("AAA", "ZZZ")),
        _event("2026-10-27T18:00:00Z", 2, 1, ("YYY", "AAA")),  # AAA pierde como visitante
        _event("2026-11-03T18:00:00Z", 0, 2, ("XXX", "AAA")),
        _event("2026-11-05T18:00:00Z", 2, 0, ("AAA", "BBB")),
        _event("2026-11-05T20:00:00Z", 0, 2, ("CCC", "DDD")),
    ]
    monkeypatch.setattr(lolesports_service, "_fetch_league_events", lambda slug: events)
    results = lolesports_service.fetch_latest_results(["les"], now=NOW, lookback_days=3)

    by_winner = {r.winner_code: r for r in results}
    assert by_winner["AAA"].winner_streak == 2  # 11/03 y 11/05; el 10/27 la perdio
    assert by_winner["DDD"].winner_streak == 1
    text = lolesports_service.format_results_tweet(results, ["les"])
    assert "🔥" not in text  # por debajo del minimo de racha


def test_streak_shown_from_three(monkeypatch):
    events = [
        _event("2026-10-27T18:00:00Z", 2, 0, ("AAA", "ZZZ")),
        _event("2026-11-03T18:00:00Z", 2, 0, ("AAA", "YYY")),
        _event("2026-11-05T18:00:00Z", 2, 1, ("AAA", "BBB")),
    ]
    monkeypatch.setattr(lolesports_service, "_fetch_league_events", lambda slug: events)
    results = lolesports_service.fetch_latest_results(["les"], now=NOW, lookback_days=3)
    assert "✅ AAA 2-1 BBB (Jornada 1) 🔥3 seguidas" in lolesports_service.format_results_tweet(results, ["les"])


def _many_results(n):
    return [
        lolesports_service.ResultInfo(NOW, "les", "Jornada 1", f"Equipo {i}", f"EQ{i}", f"Rival {i}", f"RV{i}", 2, 1)
        for i in range(n)
    ]


def test_results_tweet_trims_with_more_matches_note():
    results = _many_results(12)
    text = lolesports_service.format_results_tweet(results, ["les"], max_chars=200)
    assert len(text) <= 200 and "…y " in text and text.endswith("partidos más")
    shown = text.count("✅")
    assert f"…y {12 - shown} partidos más" in text
    assert lolesports_service.format_results_tweet(results[:2], ["les"], max_chars=200).count("✅") == 2


def test_results_thread_covers_all_and_fits(monkeypatch):
    results = _many_results(14)
    thread = lolesports_service.format_results_thread(results, ["les"], "@LESESPORTS #LES")
    assert len(thread) >= 2
    assert all(char_count.count_chars(t) <= 280 for t in thread)
    assert sum(t.count("✅") for t in thread) == 14
    assert "(1/" in thread[0] and thread[-1].endswith("@LESESPORTS #LES")


def test_results_endpoint_many_matches_returns_trimmed_content_and_thread(client, mocker):
    mocker.patch("app.routers.generate.results.fetch_latest_results", return_value=_many_results(14))
    body = client.post("/api/generate/results", json={"leagues": ["les"]}).json()

    assert body["within_limit"] is True and body["char_count"] <= 280
    assert "partidos más" in body["content"] and "@LESESPORTS" in body["content"]
    assert len(body["thread"]) >= 2


def test_results_endpoint_few_matches_has_empty_thread(client, mocker):
    mocker.patch("app.routers.generate.results.fetch_latest_results", return_value=_many_results(2))
    body = client.post("/api/generate/results", json={"leagues": ["les"]}).json()
    assert body["thread"] == [] and body["within_limit"] is True
