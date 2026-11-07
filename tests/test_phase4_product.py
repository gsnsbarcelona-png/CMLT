from datetime import datetime, timezone

import pytest

from app.services import lolesports_service, phrasing
from app.services.golgg_service import StatCandidate, format_stat_tweet_plain


def _event(start, state="completed", s1=3, s2=1, block="Jornada 1", codes=("MKF", "HRTS")):
    return {
        "startTime": start,
        "state": state,
        "type": "match",
        "blockName": block,
        "match": {
            "teams": [
                {"name": codes[0] + " Team", "code": codes[0], "result": {"outcome": "win", "gameWins": s1}},
                {"name": codes[1] + " Team", "code": codes[1], "result": {"outcome": "loss", "gameWins": s2}},
            ]
        },
    }


NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- variedad
def test_variety_off_keeps_original_question():
    assert phrasing.vary_question("¿Viste el clip?") == "¿Viste el clip?"


def test_variety_on_uses_alternatives_and_avoids_recent(monkeypatch):
    monkeypatch.setattr(phrasing, "VARIETY_ENABLED", True)
    phrasing.reset_recent()
    question = "¿Viste el clip?"
    options = {question, *phrasing.QUESTION_ALTERNATIVES[question]}
    seen = [phrasing.vary_question(question) for _ in range(len(options))]
    assert set(seen) == options  # no repite hasta agotar todas las opciones
    assert phrasing.vary_question("pregunta que no esta en la tabla") == "pregunta que no esta en la tabla"


def test_every_alternative_is_a_question_and_keys_are_unique():
    for original, alternatives in phrasing.QUESTION_ALTERNATIVES.items():
        assert original.startswith("¿") and original.endswith("?")
        assert alternatives, original
        for alt in alternatives:
            assert alt.startswith("¿") and alt.endswith("?"), alt


def test_stat_tweet_uses_varied_question_but_keeps_data(monkeypatch):
    monkeypatch.setattr(phrasing, "VARIETY_ENABLED", True)
    candidate = StatCandidate(
        kind="player_kda", subject="Escik", fact_sentence="Escik tiene 9.4 de KDA.", plano_emoji="🔥",
        plano_title="KDA", plano_question="¿Viste el clip?",
    )
    for _ in range(10):
        text = format_stat_tweet_plain(candidate)
        assert "Escik tiene 9.4 de KDA." in text
        assert text.endswith(" 🔥") and "¿" in text.splitlines()[-1]


# ---------------------------------------------------------------- resultados
def test_fetch_latest_results_picks_most_recent_day(mocker):
    events = [
        _event("2026-11-01T18:00:00Z", s1=3, s2=0, codes=("AAA", "BBB")),  # jornada vieja
        _event("2026-11-05T18:00:00Z", s1=2, s2=3, codes=("MKF", "HRTS")),  # gana el 2o
        _event("2026-11-05T20:00:00Z", s1=3, s2=1, codes=("UCAM", "BARCA")),
        _event("2026-11-06T18:00:00Z", state="unstarted"),  # sin terminar: se ignora
    ]
    mocker.patch.object(lolesports_service, "_fetch_league_events", return_value=events)

    results = lolesports_service.fetch_latest_results(["les"], now=NOW)

    assert [(r.team1_code, r.team2_code) for r in results] == [("MKF", "HRTS"), ("UCAM", "BARCA")]
    assert results[0].winner_code == "HRTS"


def test_fetch_latest_results_ignores_too_old_and_incomplete(mocker):
    events = [
        _event("2026-10-01T18:00:00Z"),  # fuera de la ventana de 7 dias
        {"startTime": "2026-11-05T18:00:00Z", "state": "completed", "type": "match", "match": {"teams": [{}, {}]}},
    ]
    mocker.patch.object(lolesports_service, "_fetch_league_events", return_value=events)
    assert lolesports_service.fetch_latest_results(["les"], now=NOW) == []


def test_format_results_tweet_puts_winner_first(mocker):
    mocker.patch.object(
        lolesports_service, "_fetch_league_events", return_value=[_event("2026-11-05T18:00:00Z", s1=2, s2=3)]
    )
    results = lolesports_service.fetch_latest_results(["les"], now=NOW)
    text = lolesports_service.format_results_tweet(results, ["les"])

    assert "Resultados LES (05/11)" in text
    assert "✅ HRTS 3-2 MKF (Jornada 1)" in text


def test_results_endpoint_returns_tweet_with_closing_tags(client, mocker):
    result = lolesports_service.ResultInfo(
        start_time=NOW, league_slug="les", block_name="Final", team1_name="A", team1_code="AAA",
        team2_name="B", team2_code="BBB", score1=3, score2=1,
    )
    mocker.patch("app.routers.generate.results.fetch_latest_results", return_value=[result])

    res = client.post("/api/generate/results", json={"leagues": ["les"]})

    assert res.status_code == 200
    body = res.json()
    assert "✅ AAA 3-1 BBB (Final)" in body["content"]
    assert "@LESESPORTS" in body["content"]
    assert body["within_limit"] is True


def test_results_endpoint_404_when_none_and_400_on_bad_league(client, mocker):
    mocker.patch("app.routers.generate.results.fetch_latest_results", return_value=[])
    assert client.post("/api/generate/results", json={"leagues": ["les"]}).status_code == 404
    assert client.post("/api/generate/results", json={"leagues": ["xx"]}).status_code == 400
    assert client.post("/api/generate/results", json={"leagues": []}).status_code == 400


def test_results_endpoint_502_when_source_fails(client, mocker):
    mocker.patch(
        "app.routers.generate.results.fetch_latest_results", side_effect=lolesports_service.LoLEsportsError("caido")
    )
    assert client.post("/api/generate/results", json={"leagues": ["les"]}).status_code == 502
