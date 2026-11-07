import os
from io import BytesIO

from PIL import Image

from app.routers import images as images_module
from app.services import card_service
from app.services.image_urls import is_allowed_image_url

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

RESULTS = {
    "title": "Resultados LES",
    "subtitle": "Jornada del 07/11 · Superliga",
    "matches": [
        {"team1": "Movistar KOI Fénix", "score1": 2, "team2": "Los Heretics", "score2": 1, "block": "Semana 5"},
        {"team1": "GIANTX Pride", "score1": 0, "team2": "Team Vitality.Bee", "score2": 2, "block": "Semana 5"},
        {"team1": "UCAM Esports Club", "score1": 2, "team2": "Movistar Riders", "score2": 0, "block": "Semana 5"},
    ],
}
TOP = {
    "title": "TOP KDA — Superliga 2026",
    "subtitle": "Mejores jugadores del split",
    "unit": "KDA",
    "entries": [
        {"name": "Peña", "value": "6.4"},
        {"name": "Nicolás Ñandú", "value": "5.9"},
        {"name": "Jesús Óscar", "value": "5.1"},
    ],
}


def _check_png(data: bytes):
    assert data.startswith(PNG_SIGNATURE)
    assert Image.open(BytesIO(data)).size == (1200, 675)


def test_render_functions_produce_png():
    _check_png(card_service.render_results_card(RESULTS["title"], RESULTS["subtitle"], RESULTS["matches"]))
    _check_png(card_service.render_top_card(TOP["title"], TOP["subtitle"], TOP["unit"], TOP["entries"]))


def test_save_sample_cards_if_requested():
    out = os.environ.get("CARD_SAMPLE_DIR")
    if not out:
        return
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "card_results.png"), "wb") as f:
        f.write(card_service.render_results_card(RESULTS["title"], RESULTS["subtitle"], RESULTS["matches"]))
    with open(os.path.join(out, "card_top.png"), "wb") as f:
        f.write(card_service.render_top_card(TOP["title"], TOP["subtitle"], TOP["unit"], TOP["entries"]))


def test_endpoints_store_valid_png(client, tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    monkeypatch.setattr(images_module, "IMAGES_DIR", images_dir)
    for path, body in (("/api/images/card/results", RESULTS), ("/api/images/card/top", TOP)):
        res = client.post(path, json=body)
        assert res.status_code == 200, res.text
        url = res.json()["image_url"]
        assert is_allowed_image_url(url)
        _check_png((images_dir / url.rsplit("/", 1)[1]).read_bytes())
    assert len(list(images_dir.iterdir())) == 2


def test_generate_payloads_feed_card_endpoints(client, mocker, tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from app.services import lolesports_service
    from tests.test_generate_top_ranking_api import _players

    monkeypatch.setattr(images_module, "IMAGES_DIR", tmp_path / "images")
    info = lolesports_service.ResultInfo(
        start_time=datetime(2026, 11, 7, 12, tzinfo=timezone.utc), league_slug="les", block_name="Final",
        team1_name="A", team1_code="AAA", team2_name="B", team2_code="BBB", score1=3, score2=1,
    )
    mocker.patch("app.routers.generate.results.fetch_latest_results", return_value=[info])
    card = client.post("/api/generate/results", json={"leagues": ["les"]}).json()["card"]
    assert card.pop("kind") == "results"
    assert client.post("/api/images/card/results", json=card).status_code == 200

    mocker.patch("app.routers.generate.top_ranking.fetch_player_stats", return_value=_players())
    card = client.post("/api/generate/top-ranking", json={"category": "player_kda"}).json()[0]["card"]
    assert card.pop("kind") == "top"
    assert client.post("/api/images/card/top", json=card).status_code == 200


def test_twelve_long_rows_still_render(client, tmp_path, monkeypatch):
    monkeypatch.setattr(images_module, "IMAGES_DIR", tmp_path / "images")
    match = {"team1": "A" * 40, "team2": "B" * 40, "score1": 2, "score2": 1, "block": "C" * 40}
    assert client.post("/api/images/card/results", json={**RESULTS, "matches": [match] * 12}).status_code == 200
    entry = {"name": "N" * 50, "value": "9" * 20}
    assert client.post("/api/images/card/top", json={**TOP, "entries": [entry] * 12}).status_code == 200


def test_validation_rejects_abuse(client, tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    monkeypatch.setattr(images_module, "IMAGES_DIR", images_dir)
    match = RESULTS["matches"][0]
    bad_results = [
        {**RESULTS, "matches": [match] * 13},
        {**RESULTS, "matches": []},
        {**RESULTS, "title": "x" * 61},
        {**RESULTS, "matches": [{**match, "team1": "x" * 41}]},
        {**RESULTS, "matches": [{**match, "score1": 1000}]},
    ]
    for body in bad_results:
        assert client.post("/api/images/card/results", json=body).status_code == 422
    entry = TOP["entries"][0]
    bad_top = [
        {**TOP, "entries": [entry] * 13},
        {**TOP, "entries": []},
        {**TOP, "entries": [{**entry, "name": "x" * 51}]},
        {**TOP, "entries": [{**entry, "value": "x" * 21}]},
        {**TOP, "unit": "x" * 31},
    ]
    for body in bad_top:
        assert client.post("/api/images/card/top", json=body).status_code == 422
    assert not images_dir.exists() or list(images_dir.iterdir()) == []
