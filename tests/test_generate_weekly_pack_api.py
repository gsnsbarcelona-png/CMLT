from datetime import datetime, timezone

from app.services import lolesports_service
from app.services.golgg_service import GolGGError
from app.services.history_service import HistoryDataError
from tests.test_generate_anniversary_api import _anniversary
from tests.test_generate_calendar_api import _match
from tests.test_generate_top_ranking_api import _players


def _result_info():
    return lolesports_service.ResultInfo(
        start_time=datetime(2026, 11, 7, 12, tzinfo=timezone.utc), league_slug="les", block_name="Final",
        team1_name="A", team1_code="AAA", team2_name="B", team2_code="BBB", score1=3, score2=1,
    )


def _patch_all(mocker):
    mocker.patch("app.routers.generate.calendar.fetch_upcoming_matches", return_value=[_match()])
    mocker.patch("app.routers.generate.results.fetch_latest_results", return_value=[_result_info()])
    mocker.patch("app.routers.generate.top_ranking.fetch_player_stats", return_value=_players())
    mocker.patch("app.routers.generate.anniversary.find_for_today", return_value=(_anniversary(), True, 0))


def test_weekly_pack_returns_four_pieces(client, mocker):
    _patch_all(mocker)

    res = client.post("/api/generate/weekly-pack", json={})

    assert res.status_code == 200
    items = res.json()["items"]
    assert [i["kind"] for i in items] == ["calendar", "results", "top-ranking", "anniversary"]
    assert all(i["error"] is None and i["content"] and i["source"] == "weekly-pack" for i in items)
    assert items[1]["card"]["kind"] == "results"
    assert items[2]["card"]["kind"] == "top"
    assert "Escik" in items[2]["content"]


def test_weekly_pack_partial_failure_keeps_other_pieces(client, mocker):
    _patch_all(mocker)
    mocker.patch("app.routers.generate.results.fetch_latest_results", return_value=[])
    mocker.patch(
        "app.routers.generate.anniversary.find_for_today", side_effect=HistoryDataError("sin datos")
    )

    items = client.post("/api/generate/weekly-pack", json={"leagues": ["les"]}).json()["items"]

    by_kind = {i["kind"]: i for i in items}
    assert by_kind["results"]["content"] is None and "No hay resultados" in by_kind["results"]["error"]
    assert by_kind["anniversary"]["error"] == "sin datos"
    assert by_kind["calendar"]["content"] and by_kind["calendar"]["error"] is None
    assert by_kind["top-ranking"]["content"]


def test_weekly_pack_top_falls_back_to_next_category(client, mocker):
    _patch_all(mocker)
    mocker.patch("app.routers.generate.top_ranking.fetch_player_stats", side_effect=GolGGError("caído"))
    mocker.patch("app.routers.generate.top_ranking.fetch_team_stats", side_effect=GolGGError("caído"))

    top = next(i for i in client.post("/api/generate/weekly-pack", json={}).json()["items"] if i["kind"] == "top-ranking")

    assert top["content"] is None and top["error"] == "caído"


def test_weekly_pack_unexpected_exception_is_contained(client, mocker):
    _patch_all(mocker)
    mocker.patch("app.routers.generate.calendar.fetch_upcoming_matches", side_effect=RuntimeError("boom"))

    items = client.post("/api/generate/weekly-pack", json={}).json()["items"]

    assert items[0]["error"] and "boom" not in items[0]["error"]
    assert items[1]["content"]


def test_weekly_pack_rejects_unknown_league(client):
    assert client.post("/api/generate/weekly-pack", json={"leagues": ["lck"]}).status_code == 400
