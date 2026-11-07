from app.services.ai_service import AIGenerationError
from app.services.history_service import Anniversary, HistoryDataError


def _anniversary():
    return Anniversary(
        month=8,
        day=12,
        year=2021,
        headline="Vodafone Giants campeon",
        detail="3-1 a UCAM Esports Club.",
        era_name="Superliga",
        teams=["Vodafone Giants", "UCAM Esports Club"],
        today_connection="GIANTX sigue compitiendo hoy.",
        source="COPE",
    )


def test_anniversary_default_style_is_plain_and_does_not_save_drafts(client, mocker):
    # La efemeride ya no auto-guarda -- el usuario elige que version guardar
    # con el boton "Guardar" de su tarjeta (POST /api/tweets).
    mocker.patch("app.routers.generate.anniversary.find_for_today", return_value=(_anniversary(), True, 0))
    ai_mock = mocker.patch("app.routers.generate.anniversary.generate_anniversary_tweet")
    ai_quick_mock = mocker.patch("app.routers.generate.anniversary.generate_anniversary_quick_fact")

    res = client.post("/api/generate/anniversary", json={})

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["format"] == "completo"
    assert body[1]["format"] == "dato_rapido"
    assert all(item["error"] is None for item in body)
    assert "draft_id" not in body[0]
    assert body[0]["suggested_teams"] == ["Vodafone Giants", "UCAM Esports Club"]
    ai_mock.assert_not_called()
    ai_quick_mock.assert_not_called()

    drafts = client.get("/api/tweets?status=draft").json()
    assert len(drafts) == 0


def test_anniversary_plain_marks_is_exact(client, mocker):
    mocker.patch("app.routers.generate.anniversary.find_for_today", return_value=(_anniversary(), False, 3))

    res = client.post("/api/generate/anniversary", json={"style": "plain"})

    body = res.json()
    assert all(item["is_exact"] is False for item in body)
    assert "no es de hoy" in body[1]["content"] or "No hay efemeride" in body[0]["content"]


def test_anniversary_ai_style_returns_two_variants(client, mocker):
    mocker.patch("app.routers.generate.anniversary.find_for_today", return_value=(_anniversary(), True, 0))
    full_mock = mocker.patch("app.routers.generate.anniversary.generate_anniversary_tweet", return_value="Tweet completo")
    quick_mock = mocker.patch("app.routers.generate.anniversary.generate_anniversary_quick_fact", return_value="Tweet corto")

    res = client.post("/api/generate/anniversary", json={"style": "ai"})

    assert res.status_code == 200
    body = res.json()
    assert body[0]["content"].startswith("Tweet completo")
    assert body[1]["content"].startswith("Tweet corto")
    full_mock.assert_called_once()
    quick_mock.assert_called_once()


def test_anniversary_partial_ai_failure_still_returns_the_other(client, mocker):
    mocker.patch("app.routers.generate.anniversary.find_for_today", return_value=(_anniversary(), True, 0))
    mocker.patch(
        "app.routers.generate.anniversary.generate_anniversary_tweet",
        side_effect=AIGenerationError("Falta configurar ANTHROPIC_API_KEY"),
    )
    mocker.patch("app.routers.generate.anniversary.generate_anniversary_quick_fact", return_value="Tweet corto")

    res = client.post("/api/generate/anniversary", json={"style": "ai"})

    assert res.status_code == 200
    body = res.json()
    assert body[0]["format"] == "completo"
    assert body[0]["error"] is not None
    assert body[0]["content"] is None
    assert body[1]["format"] == "dato_rapido"
    assert body[1]["error"] is None
    assert body[1]["content"].startswith("Tweet corto")


def test_anniversary_rejects_unknown_style(client):
    res = client.post("/api/generate/anniversary", json={"style": "flashy"})
    assert res.status_code == 400


def test_anniversary_no_data_returns_502(client, mocker):
    mocker.patch(
        "app.routers.generate.anniversary.find_for_today", side_effect=HistoryDataError("no hay datos cargados")
    )

    res = client.post("/api/generate/anniversary", json={})

    assert res.status_code == 502


def test_anniversary_includes_league_and_hashtag_closing(client, mocker):
    mocker.patch("app.routers.generate.anniversary.find_for_today", return_value=(_anniversary(), True, 0))

    res = client.post("/api/generate/anniversary", json={})

    content = res.json()[0]["content"]
    assert "@LESESPORTS" in content
    assert "#OnThisDay" in content
    assert "#LT" in content
