import httpx
import pytest

from app.config import settings
from app.services import golgg_service
from app.services.golgg_service import GolGGError, fetch_team_stats, get_active_config

S16 = [
    {"trname": "EMEA Masters 2026 Summer Main Event", "region": "WR", "firstgame": "2026-09-26"},
    {"trname": "EMEA Masters 2026 Summer LCQ", "region": "WR", "firstgame": "2026-09-21"},
    {"trname": "LEC 2026 Summer Playoffs", "region": "EUW", "firstgame": "2026-09-05"},
    {"trname": "LES 2026 Final Four", "region": "ES", "firstgame": "2026-09-01"},
    {"trname": "LEC 2026 Summer Season", "region": "EUW", "firstgame": "2026-07-24"},
    {"trname": "LES 2026 Summer Playoffs", "region": "ES", "firstgame": "2026-08-18"},
    {"trname": "LES 2026 Summer", "region": "ES", "firstgame": "2026-07-14"},
    {"trname": "LES 2026 Spring", "region": "ES", "firstgame": "2026-04-08"},
    {"trname": "EMEA Masters 2026 Winter", "region": "WR", "firstgame": "2026-03-09"},
]
S17 = [{"trname": "LES 2027 Kick-off Tournament", "region": "ES", "firstgame": "2027-02-13"}]


@pytest.fixture()
def autodiscover(monkeypatch):
    monkeypatch.setattr(settings, "golgg_autodiscover", True)
    golgg_service.reset_active_config_cache()


def test_autodiscover_picks_latest_regular_les_and_all_les_of_season(autodiscover, mocker):
    mocker.patch(
        "app.services.golgg_service.discover_tournaments",
        side_effect=lambda season, region=None: S16 if season == "S16" else [],
    )
    config = get_active_config()

    assert config.season == "S16"
    assert config.tournament == "LES 2026 Summer"  # no Playoffs ni Final Four
    assert config.year_tournaments == [
        "LES 2026 Spring", "LES 2026 Summer", "LES 2026 Summer Playoffs", "LES 2026 Final Four",
    ]
    assert config.lec_tournament == "LEC 2026 Summer Season"
    assert "EMEA Masters 2026 Summer Main Event" in config.emea_masters_tournaments
    assert len(config.emea_masters_tournaments) == 3


def test_autodiscover_moves_to_next_season_when_it_has_les(autodiscover, mocker):
    mocker.patch(
        "app.services.golgg_service.discover_tournaments",
        side_effect=lambda season, region=None: {"S16": S16, "S17": S17}.get(season, []),
    )
    config = get_active_config()

    assert config.season == "S17"
    assert config.tournament == "LES 2027 Kick-off Tournament"
    # Sin LEC/EMEA nuevos todavia, cae a lo configurado.
    assert config.lec_tournament == settings.lec_tournament


def test_autodiscover_falls_back_to_settings_when_gol_gg_fails(autodiscover, mocker):
    mocker.patch("app.services.golgg_service.discover_tournaments", side_effect=GolGGError("caido"))

    config = get_active_config()

    assert config.tournament == settings.golgg_tournament
    assert config.season == settings.golgg_season


def test_autodiscover_is_cached(autodiscover, mocker):
    discover = mocker.patch(
        "app.services.golgg_service.discover_tournaments",
        side_effect=lambda season, region=None: S16 if season == "S16" else [],
    )
    get_active_config()
    calls = discover.call_count
    get_active_config()
    assert discover.call_count == calls


def test_cached_get_retries_on_5xx_then_succeeds(mocker):
    mocker.patch("app.services.golgg_service._RETRY_BACKOFF_SECONDS", 0)
    ok = mocker.Mock(text="<html>ok</html>")
    ok.raise_for_status = lambda: None
    bad = httpx.Response(503, request=httpx.Request("GET", "https://gol.gg/x"))
    get = mocker.patch("httpx.get", side_effect=[bad, ok])

    assert golgg_service._cached_get("https://gol.gg/x") == "<html>ok</html>"
    assert get.call_count == 2


def test_cached_get_does_not_retry_on_403_and_explains_rate_limit(mocker):
    mocker.patch("app.services.golgg_service._RETRY_BACKOFF_SECONDS", 0)
    forbidden = httpx.Response(403, request=httpx.Request("GET", "https://gol.gg/x"))
    get = mocker.patch("httpx.get", return_value=forbidden)

    with pytest.raises(GolGGError, match="limitando"):
        golgg_service._cached_get("https://gol.gg/x")
    assert get.call_count == 1


def test_cached_get_serves_stale_copy_when_source_is_down(mocker):
    mocker.patch("app.services.golgg_service._RETRY_BACKOFF_SECONDS", 0)
    golgg_service._http_cache["https://gol.gg/x"] = (-10_000.0, "<html>vieja</html>")
    mocker.patch("httpx.get", side_effect=httpx.ConnectError("boom"))

    assert golgg_service._cached_get("https://gol.gg/x") == "<html>vieja</html>"


def test_fetch_team_stats_reports_format_change_when_all_rows_dropped(mocker):
    html = (
        '<table class="playerslist"><tr><th>Name</th><th>Games</th><th>CAMBIADO</th></tr>'
        "<tr><td>UCAM</td><td>10</td><td>x</td></tr></table>"
    )
    mocker.patch("app.services.golgg_service._cached_get", return_value=html)

    with pytest.raises(GolGGError, match="cambiado el formato"):
        fetch_team_stats("LES 2026 Summer")
