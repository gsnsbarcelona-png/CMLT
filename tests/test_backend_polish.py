import threading
import time
from datetime import datetime, timezone
from io import BytesIO

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.routers.generate.league_comparison import _with_lec_handle
from app.services import image_service, lolesports_service, ranked_service
from app.services.golgg_service import PlayerStat, TeamStat
from app.services.image_urls import LOCAL_IMAGE_RE

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------ 1) GRAN FINAL
def _event(start, block, s1=3, s2=1, state="completed", codes=("MKF", "HRTS")):
    return {
        "startTime": start, "state": state, "type": "match", "blockName": block,
        "match": {"teams": [
            {"name": codes[0], "code": codes[0], "result": {"gameWins": s1}},
            {"name": codes[1], "code": codes[1], "result": {"gameWins": s2}},
        ]},
    }


def test_results_relabel_gran_final_across_all_finals(monkeypatch):
    events = [
        _event("2026-10-20T15:00:00Z", "Final", codes=("AAA", "BBB")),  # fuera de la ventana de 7 dias
        _event("2026-10-21T15:00:00Z", "Final", codes=("CCC", "DDD")),
        _event("2026-11-06T15:00:00Z", "Final", codes=("EEE", "FFF")),  # la ultima: GRAN FINAL
    ]
    monkeypatch.setattr(lolesports_service, "_fetch_league_events", lambda slug: events)
    results = lolesports_service.fetch_latest_results(["les"], now=NOW)
    assert [r.block_name for r in results] == ["GRAN FINAL"]
    text = lolesports_service.format_results_tweet(results, ["les"])
    assert "🏆 EEE 3-1 FFF (GRAN FINAL)" in text
    assert "✅" not in text


def test_results_previous_finals_labelled_cruce(monkeypatch):
    events = [
        _event("2026-11-05T15:00:00Z", "Final", codes=("AAA", "BBB")),
        _event("2026-11-06T15:00:00Z", "Final", codes=("CCC", "DDD")),
        _event("2026-11-08T15:00:00Z", "Final", state="unstarted", codes=("TBD", "TBD")),  # la futura es la gran final
    ]
    monkeypatch.setattr(lolesports_service, "_fetch_league_events", lambda slug: events)
    results = lolesports_service.fetch_latest_results(["les"], now=NOW, lookback_days=3)
    assert [r.block_name for r in results] == ["Final Four - Cruce 2"]
    assert "✅ CCC 3-1 DDD (Final Four - Cruce 2)" in lolesports_service.format_results_tweet(results, ["les"])


# ------------------------------------------------------------ 2) @LEC
def test_lec_handle_added_after_les():
    out = _with_lec_handle(f"{settings.league_handle_les} #LT")
    assert out.split(" ")[:2] == [settings.league_handle_les, settings.league_handle_lec]
    assert _with_lec_handle(out) == out  # idempotente


def test_league_comparison_endpoint_closing_includes_lec(client, mocker):
    team = TeamStat(
        name="UCAM Esports", games=15, win_rate=86.7, kda=2.13, gpm=2157, fb_pct=66.7, towers_killed=8.9,
        dragons_per_game=2.5, avg_game_duration_seconds=1750,
    )
    lec = TeamStat(
        name="Fnatic", games=20, win_rate=50.0, kda=1.5, gpm=2100, fb_pct=55.0, towers_killed=8.0,
        dragons_per_game=2.2, avg_game_duration_seconds=1800,
    )
    pl = PlayerStat(name="Escik", games=15, win_rate=86.7, kda=9.4, csm=9.2, avg_kills=6.7, penta_kills=0, solo_kills=8)
    pl2 = PlayerStat(name="Caps", games=20, win_rate=55.0, kda=4.0, csm=9.5, avg_kills=4.5, penta_kills=0, solo_kills=2)
    mocker.patch("app.routers.generate.league_comparison.fetch_team_stats", side_effect=[[team], [lec]])
    mocker.patch("app.routers.generate.league_comparison.fetch_player_stats", side_effect=[[pl], [pl2]])

    body = client.post("/api/generate/league-comparison", json={}).json()
    for variant in body:
        assert settings.league_handle_les in variant["content"]
        assert settings.league_handle_lec in variant["content"]


# ------------------------------------------------------------ 3) imagenes
def _png(color=(255, 0, 0, 255)) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (50, 50), color).save(buf, format="PNG")
    return buf.getvalue()


def test_logo_bytes_cached_and_ttl(mocker):
    resp = mocker.Mock(content=b"abc", raise_for_status=lambda: None)
    get = mocker.patch("app.services.image_service.httpx.get", return_value=resp)
    assert image_service.fetch_logo_bytes("http://x/a.png") == b"abc"
    assert image_service.fetch_logo_bytes("http://x/a.png") == b"abc"
    assert get.call_count == 1
    image_service._logo_cache["http://x/a.png"] = (time.monotonic() - 99999, b"old")
    image_service.fetch_logo_bytes("http://x/a.png")
    assert get.call_count == 2


def test_logo_cache_has_max_entries(mocker, monkeypatch):
    monkeypatch.setattr(image_service, "LOGO_CACHE_MAX_ENTRIES", 3)
    mocker.patch(
        "app.services.image_service.httpx.get",
        return_value=mocker.Mock(content=b"z", raise_for_status=lambda: None),
    )
    for i in range(10):
        image_service.fetch_logo_bytes(f"http://x/{i}.png")
    assert len(image_service._logo_cache) <= 3


def test_logos_downloaded_in_parallel(mocker):
    barrier = threading.Barrier(2, timeout=5)

    def fake_get(url, **kw):
        barrier.wait()  # solo pasa si las dos descargas corren a la vez
        return mocker.Mock(content=url.encode(), raise_for_status=lambda: None)

    mocker.patch("app.services.image_service.httpx.get", side_effect=fake_get)
    assert image_service.fetch_logos_parallel(["http://x/a", "http://x/b"]) == [b"http://x/a", b"http://x/b"]


def test_deterministic_name_matches_local_regex():
    name = image_service.deterministic_image_name("vs", "http://x/a.png", "http://x/b.png")
    assert LOCAL_IMAGE_RE.fullmatch(f"/data/images/{name}")
    assert name == image_service.deterministic_image_name("vs", "http://x/a.png", "http://x/b.png")
    assert name != image_service.deterministic_image_name("vs", "http://x/b.png", "http://x/a.png")
    assert name != image_service.deterministic_image_name("branded", "http://x/a.png", "http://x/b.png")


def test_team_vs_logo_reuses_file_and_skips_download(client, mocker, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routers.generate.stats.IMAGES_DIR", tmp_path)
    mocker.patch(
        "app.routers.generate.stats.get_les_team_logo_url",
        side_effect=lambda t: f"http://static.lolesports.com/{t}.png",
    )
    get = mocker.patch(
        "app.services.image_service.httpx.get",
        return_value=mocker.Mock(content=_png(), raise_for_status=lambda: None),
    )
    params = {"team_a": "A", "team_b": "B"}
    r1 = client.get("/api/generate/team-vs-logo", params=params).json()["image_url"]
    r2 = client.get("/api/generate/team-vs-logo", params=params).json()["image_url"]
    assert r1 == r2 and LOCAL_IMAGE_RE.fullmatch(r1)
    assert get.call_count == 2  # solo la primera vez (2 escudos)
    assert len(list(tmp_path.glob("*.png"))) == 1


def test_branded_image_deterministic_and_bytes_cached(client, mocker, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routers.generate.stats.IMAGES_DIR", tmp_path)
    mocker.patch("app.routers.generate.stats.get_les_team_logo_url", return_value="http://static.lolesports.com/a.png")
    get = mocker.patch(
        "app.services.image_service.httpx.get",
        return_value=mocker.Mock(content=_png(), raise_for_status=lambda: None),
    )
    mocker.patch("app.routers.generate.stats.compose_branded_image", return_value=b"png")
    u1 = client.get("/api/generate/branded-image", params={"team_a": "A"}).json()["image_url"]
    u2 = client.get("/api/generate/branded-image", params={"team_a": "A"}).json()["image_url"]
    assert u1 == u2 and LOCAL_IMAGE_RE.fullmatch(u1)
    assert get.call_count == 1  # segunda vez: bytes en cache


def test_branding_images_loaded_once(monkeypatch, tmp_path):
    bg, logo = tmp_path / "bg.png", tmp_path / "logo.png"
    Image.new("RGBA", (400, 200), (10, 20, 30, 255)).save(bg)
    Image.new("RGBA", (40, 40), (255, 255, 255, 255)).save(logo)
    monkeypatch.setattr(image_service, "BRANDING_BACKGROUND_PATH", bg)
    monkeypatch.setattr(image_service, "BRANDING_LOGO_PATH", logo)
    image_service._branding_cache.clear()
    opened = []
    real_open = Image.open

    def spy(*a, **k):
        opened.append(a[0])
        return real_open(*a, **k)

    monkeypatch.setattr(image_service.Image, "open", spy)
    image_service.compose_branded_image()
    image_service.compose_branded_image()
    assert len(opened) == 2  # una vez cada archivo, no por llamada


# ------------------------------------------------------------ 4) lolpros
def _resp(status, text=""):
    return httpx.Response(status, request=httpx.Request("GET", "https://lolpros.gg/x"), text=text)


@pytest.mark.parametrize("status", [429, 403])
def test_rate_limit_raises_ranked_error_and_is_unresolved(mocker, status, caplog):
    get = mocker.patch("app.services.ranked_service.httpx.get", return_value=_resp(status))
    with pytest.raises(ranked_service.RankedError, match="limitando"):
        ranked_service._cached_get("https://lolpros.gg/player/a")
    ranks, unresolved = ranked_service.fetch_all_player_ranks(["a"])
    assert ranks == [] and unresolved == ["a"]
    assert get.call_count == 2  # una por llamada, sin reintentos internos
    assert str(status) in caplog.text


@pytest.mark.parametrize("status", [404, 500])
def test_not_found_is_negative_cached(mocker, status):
    get = mocker.patch("app.services.ranked_service.httpx.get", return_value=_resp(status))
    assert ranked_service._cached_get("https://lolpros.gg/player/z") == (status, "")
    assert ranked_service._cached_get("https://lolpros.gg/player/z") == (status, "")
    assert get.call_count == 1
    ranked_service._negative_cache["https://lolpros.gg/player/z"] = (time.monotonic() - 9999, status)
    ranked_service._cached_get("https://lolpros.gg/player/z")
    assert get.call_count == 2


def test_ranked_caches_have_max_entries(mocker, monkeypatch):
    monkeypatch.setattr(ranked_service, "_CACHE_MAX_ENTRIES", 5)
    mocker.patch("app.services.ranked_service.httpx.get", return_value=_resp(200, "ok"))
    for i in range(20):
        ranked_service._cached_get(f"https://lolpros.gg/player/{i}")
    assert len(ranked_service._http_cache) <= 5
