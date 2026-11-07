from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services.lolesports_service import (
    LoLEsportsError,
    MatchInfo,
    TeamRosterNotFoundError,
    build_matches_context,
    closing_tags,
    fetch_les_team_roster,
    fetch_les_team_roster_with_roles,
    fetch_matches_today_or_tomorrow,
    fetch_todays_matches,
    fetch_upcoming_matches,
    format_schedule_tweet,
    get_les_team_logo_url,
    league_label,
)

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _match_event(state, start_time, team1=("Team A", "TMA"), team2=("Team B", "TMB"), block="Grupos", event_type="match"):
    teams = []
    for team in (team1, team2):
        if team is None:
            teams.append(None)
        else:
            teams.append({"name": team[0], "code": team[1]})
    return {
        "startTime": _iso(start_time),
        "state": state,
        "type": event_type,
        "blockName": block,
        "league": {"name": "LES", "slug": "les"},
        "match": {"teams": teams},
    }


class _FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def _events_response(events):
    return _FakeResponse({"data": {"schedule": {"events": events}}})


def test_filters_by_state_and_horizon(mocker):
    events = [
        _match_event("unstarted", NOW + timedelta(days=2)),  # dentro de la ventana -> incluido
        _match_event("completed", NOW - timedelta(days=1)),  # ya jugado -> excluido
        _match_event("unstarted", NOW + timedelta(days=10)),  # fuera de la ventana -> excluido
        _match_event("inProgress", NOW - timedelta(hours=1)),  # en vivo -> incluido pese a ser "pasado"
        _match_event("unstarted", NOW + timedelta(days=1), event_type="other"),  # no es partido -> excluido
    ]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_events_response(events))

    matches = fetch_upcoming_matches(["les"], now=NOW)

    assert len(matches) == 2
    assert {m.state for m in matches} == {"unstarted", "inProgress"}


def test_includes_match_late_on_the_seventh_calendar_day(mocker):
    # "now" es temprano a la mañana; el partido cae el 7mo dia de calendario
    # pero mas tarde en el dia que "now" -> con una ventana rigida de 168hs
    # quedaria afuera por error (bug real detectado con la final LES vs Heretics).
    early_morning_now = datetime(2026, 8, 30, 3, 19, tzinfo=timezone.utc)
    late_match = early_morning_now + timedelta(days=7, hours=7)
    events = [_match_event("unstarted", late_match)]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_events_response(events))

    matches = fetch_upcoming_matches(["les"], now=early_morning_now)

    assert len(matches) == 1


def test_tbd_team_parsed_when_missing(mocker):
    events = [_match_event("unstarted", NOW + timedelta(days=1), team2=None)]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_events_response(events))

    matches = fetch_upcoming_matches(["les"], now=NOW)

    assert matches[0].team2_name == "TBD"
    assert matches[0].team2_code == "TBD"


def test_converts_to_madrid_time_and_combines_leagues_sorted(mocker):
    les_events = [_match_event("unstarted", NOW + timedelta(days=2))]
    lec_events = [_match_event("unstarted", NOW + timedelta(days=1))]

    def fake_get(url, params, headers, timeout):
        events = les_events if params["leagueId"] == "105266074488398661" else lec_events
        return _events_response(events)

    mocker.patch("app.services.lolesports_service.httpx.get", side_effect=fake_get)

    matches = fetch_upcoming_matches(["les", "lec"], now=NOW)

    assert len(matches) == 2
    assert matches[0].start_time < matches[1].start_time
    assert matches[0].start_time.tzinfo is not None
    # Madrid esta en UTC+2 en agosto (horario de verano)
    assert matches[0].start_time.utcoffset() == timedelta(hours=2)


def test_relabels_final_four_king_of_the_hill_bracket(mocker):
    # 3 partidos con blockName "Final" (asi los devuelve la API real para la
    # Final Four) -> solo el ultimo cronologicamente es la gran final.
    events = [
        _match_event("unstarted", NOW + timedelta(days=2), block="Final", team1=("UCAM", "UCAM"), team2=("Barca", "BAR")),
        _match_event("unstarted", NOW + timedelta(days=3), block="Final", team1=("Ganador", "TBD"), team2=("MKF", "MKF")),
        _match_event("unstarted", NOW + timedelta(days=7), block="Final", team1=("Ganador", "TBD"), team2=("Heretics", "HRTS")),
    ]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_events_response(events))

    matches = fetch_upcoming_matches(["les"], now=NOW)

    assert [m.block_name for m in matches] == ["Final Four - Cruce 1", "Final Four - Cruce 2", "GRAN FINAL"]


def test_single_final_match_is_not_relabeled(mocker):
    events = [_match_event("unstarted", NOW + timedelta(days=2), block="Final")]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_events_response(events))

    matches = fetch_upcoming_matches(["les"], now=NOW)

    assert matches[0].block_name == "Final"


def test_http_error_wrapped(mocker):
    mocker.patch("app.services.lolesports_service.httpx.get", side_effect=httpx.ConnectError("boom"))

    with pytest.raises(LoLEsportsError):
        fetch_upcoming_matches(["les"], now=NOW)


def test_fetch_todays_matches_filters_by_madrid_date(mocker):
    events = [
        _match_event("unstarted", NOW),  # hoy
        _match_event("unstarted", NOW + timedelta(days=1)),  # mañana -> excluido
        _match_event("inProgress", NOW - timedelta(hours=2)),  # hoy, mas temprano, en vivo
    ]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_events_response(events))

    matches = fetch_todays_matches(["les"], now=NOW)

    assert len(matches) == 2
    assert all(m.state in ("unstarted", "inProgress") for m in matches)


def test_fetch_todays_matches_empty_when_none_today(mocker):
    events = [_match_event("unstarted", NOW + timedelta(days=2))]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_events_response(events))

    assert fetch_todays_matches(["les"], now=NOW) == []


def test_fetch_matches_today_or_tomorrow_includes_both_days(mocker):
    events = [
        _match_event("unstarted", NOW),  # hoy
        _match_event("unstarted", NOW + timedelta(days=1)),  # mañana -> incluido
        _match_event("unstarted", NOW + timedelta(days=2)),  # pasado mañana -> excluido
    ]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_events_response(events))

    matches = fetch_matches_today_or_tomorrow(["les"], now=NOW)

    assert len(matches) == 2


def test_fetch_matches_today_or_tomorrow_empty_when_none(mocker):
    events = [_match_event("unstarted", NOW + timedelta(days=3))]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_events_response(events))

    assert fetch_matches_today_or_tomorrow(["les"], now=NOW) == []


def _match_info(start_time, state="unstarted", league_slug="les", block_name="Grupos", codes=("MKF", "UCAM")):
    return MatchInfo(
        start_time=start_time,
        state=state,
        league_slug=league_slug,
        block_name=block_name,
        team1_name=codes[0],
        team1_code=codes[0],
        team2_name=codes[1],
        team2_code=codes[1],
    )


def test_format_empty_list():
    text = format_schedule_tweet([], ["les"])
    assert text == "No hay partidos programados de LES en los proximos 7 dias."


def test_format_single_league_and_day_abbreviation():
    match = _match_info(datetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc))
    text = format_schedule_tweet([match], ["les"])

    assert "📅 Calendario LES (01/09 al 01/09)" in text
    assert "Mar 01/09 17:00 MKF 🆚 UCAM (Grupos)" in text


def test_format_both_leagues_header_order():
    match = _match_info(datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc), league_slug="lec")
    text = format_schedule_tweet([match], ["lec", "les"])

    assert text.startswith("📅 Calendario LES + LEC")


def test_closing_tags_single_league(monkeypatch):
    import app.services.lolesports_service as lolesports_service

    monkeypatch.setattr(lolesports_service.settings, "league_handle_les", "@LESESPORTS")
    monkeypatch.setattr(lolesports_service.settings, "custom_hashtags", "#LT")

    assert closing_tags(["les"]) == "@LESESPORTS #LES #LT"


def test_closing_tags_both_leagues_order(monkeypatch):
    import app.services.lolesports_service as lolesports_service

    monkeypatch.setattr(lolesports_service.settings, "league_handle_les", "@LESESPORTS")
    monkeypatch.setattr(lolesports_service.settings, "league_handle_lec", "@LEC")
    monkeypatch.setattr(lolesports_service.settings, "custom_hashtags", "#LT")

    assert closing_tags(["lec", "les"]) == "@LESESPORTS @LEC #LES #LEC #LT"


def test_closing_tags_emea_masters_hashtag_has_no_space(monkeypatch):
    # "EMEA Masters" (LEAGUE_LABELS) tiene espacio -- el hashtag de cierre
    # usa LEAGUE_HASHTAGS ("EMEAMasters") para que siga siendo un hashtag
    # valido, igual que lo usa la cuenta oficial en sus propios tweets.
    import app.services.lolesports_service as lolesports_service

    monkeypatch.setattr(lolesports_service.settings, "league_handle_emea_masters", "@EMEAmasters")
    monkeypatch.setattr(lolesports_service.settings, "custom_hashtags", "#LT")

    assert closing_tags(["emea_masters"]) == "@EMEAmasters #EMEAMasters #LT"


def test_format_live_prefix():
    match = _match_info(datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc), state="inProgress")
    text = format_schedule_tweet([match], ["les"])

    assert "🔴 EN VIVO Dom 30/08 12:00 MKF 🆚 UCAM" in text


def test_format_renames_tbd_to_ganador():
    match = _match_info(datetime(2026, 9, 2, 17, 0, tzinfo=timezone.utc), codes=("TBD", "MKF"))
    text = format_schedule_tweet([match], ["les"])

    assert "Ganador 🆚 MKF" in text
    assert "TBD" not in text


def test_format_gran_final_gets_trophy_prefix():
    match = _match_info(datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc), block_name="GRAN FINAL")
    text = format_schedule_tweet([match], ["les"])

    assert "🏆 Dom 06/09 12:00 MKF 🆚 UCAM (GRAN FINAL)" in text


def test_league_label():
    assert league_label(["les"]) == "LES"
    assert league_label(["lec"]) == "LEC"
    assert league_label(["lec", "les"]) == "LES + LEC"
    assert league_label(["emea_masters", "les"]) == "LES + EMEA Masters"


def test_build_matches_context_empty():
    assert build_matches_context([]) == "No hay partidos programados en los proximos 7 dias."


def test_build_matches_context_lists_matches():
    match = _match_info(datetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc))
    context = build_matches_context([match])

    assert context == "Mar 01/09 17:00 MKF 🆚 UCAM (Grupos)"


def _team_entry(name, code, league_name="LES", players=("Escik", "Andariel"), roles=None, image=None):
    roles = roles or [""] * len(players)
    return {
        "name": name,
        "code": code,
        "homeLeague": {"name": league_name},
        "players": [{"summonerName": p, "role": r} for p, r in zip(players, roles)],
        "image": image,
    }


def _teams_response(teams):
    return _FakeResponse({"data": {"teams": teams}})


def test_fetch_les_team_roster_exact_name_match(mocker):
    teams = [_team_entry("UCAM Esports", "UCAM", players=("Escik", "Andariel", "Kozi"))]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_teams_response(teams))

    roster = fetch_les_team_roster("UCAM Esports")

    assert roster == ["Escik", "Andariel", "Kozi"]


def test_fetch_les_team_roster_with_roles(mocker):
    teams = [
        _team_entry(
            "UCAM Esports", "UCAM", players=("Escik", "Andariel"), roles=("mid", "bottom")
        )
    ]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_teams_response(teams))

    roster = fetch_les_team_roster_with_roles("UCAM Esports")

    assert [(p.name, p.role) for p in roster] == [("Escik", "mid"), ("Andariel", "bottom")]


def test_fetch_les_team_roster_matches_by_code_and_accents(mocker):
    teams = [_team_entry("Barça Esports", "FCB", players=("Player1", "Player2"))]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_teams_response(teams))

    assert fetch_les_team_roster("Barca eSports") == ["Player1", "Player2"]
    assert fetch_les_team_roster("fcb") == ["Player1", "Player2"]


def test_fetch_les_team_roster_ignores_other_leagues(mocker):
    teams = [
        _team_entry("Fnatic", "FNC", league_name="LEC", players=("Caps",)),
        _team_entry("UCAM Esports", "UCAM", players=("Escik",)),
    ]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_teams_response(teams))

    with pytest.raises(TeamRosterNotFoundError):
        fetch_les_team_roster("Fnatic")

    assert fetch_les_team_roster("UCAM Esports") == ["Escik"]


def test_fetch_les_team_roster_not_found_raises(mocker):
    teams = [_team_entry("UCAM Esports", "UCAM")]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_teams_response(teams))

    with pytest.raises(TeamRosterNotFoundError):
        fetch_les_team_roster("Un Equipo Que No Existe")


def test_fetch_les_team_roster_network_error_raises_lolesports_error(mocker):
    mocker.patch("app.services.lolesports_service.httpx.get", side_effect=httpx.ConnectError("boom"))

    with pytest.raises(LoLEsportsError):
        fetch_les_team_roster("UCAM Esports")


def test_fetch_les_team_roster_caches_getteams(mocker):
    teams = [_team_entry("UCAM Esports", "UCAM")]
    get_mock = mocker.patch("app.services.lolesports_service.httpx.get", return_value=_teams_response(teams))

    fetch_les_team_roster("UCAM Esports")
    fetch_les_team_roster("UCAM Esports")

    get_mock.assert_called_once()


def test_get_les_team_logo_url_returns_image_field(mocker):
    teams = [_team_entry("UCAM Esports", "UCAM", image="http://static.lolesports.com/teams/ucam.png")]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_teams_response(teams))

    assert get_les_team_logo_url("UCAM Esports") == "http://static.lolesports.com/teams/ucam.png"


def test_get_les_team_logo_url_matches_by_substring_and_accents(mocker):
    teams = [_team_entry("Barça Esports", "FCB", image="http://static.lolesports.com/teams/bar.png")]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_teams_response(teams))

    assert get_les_team_logo_url("Barca eSports") == "http://static.lolesports.com/teams/bar.png"


def test_get_les_team_logo_url_returns_none_when_team_not_found(mocker):
    teams = [_team_entry("UCAM Esports", "UCAM", image="http://static.lolesports.com/teams/ucam.png")]
    mocker.patch("app.services.lolesports_service.httpx.get", return_value=_teams_response(teams))

    assert get_les_team_logo_url("Un Equipo Que No Existe") is None


def test_get_les_team_logo_url_returns_none_on_network_error(mocker):
    mocker.patch("app.services.lolesports_service.httpx.get", side_effect=httpx.ConnectError("boom"))

    # best-effort: nunca levanta, solo devuelve None (es una sugerencia, no
    # debe romper la generacion/publicacion del tweet).
    assert get_les_team_logo_url("UCAM Esports") is None
