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


def test_anniversary_returns_two_variants_and_does_not_save_drafts(client, mocker):
    # La efemeride ya no auto-guarda -- el usuario elige que version guardar
    # con el boton "Guardar" de su tarjeta (POST /api/tweets).
    mocker.patch("app.routers.generate.anniversary.find_for_today", return_value=(_anniversary(), True, 0))

    res = client.post("/api/generate/anniversary", json={})

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["format"] == "completo"
    assert body[1]["format"] == "dato_rapido"
    assert "draft_id" not in body[0]
    assert body[0]["suggested_teams"] == ["Vodafone Giants", "UCAM Esports Club"]

    drafts = client.get("/api/tweets?status=draft").json()
    assert len(drafts) == 0


def test_anniversary_plain_marks_is_exact(client, mocker):
    mocker.patch("app.routers.generate.anniversary.find_for_today", return_value=(_anniversary(), False, 3))

    res = client.post("/api/generate/anniversary", json={})

    body = res.json()
    assert all(item["is_exact"] is False for item in body)
    assert "no es de hoy" in body[1]["content"] or "No hay efemeride" in body[0]["content"]






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
