from app.services.ai_service import AIGenerationError


def test_batch_generates_without_saving_drafts(client, mocker):
    # El lote ya no auto-guarda -- cada tweet se guarda a mano con el boton
    # "Guardar" de su tarjeta (POST /api/tweets, mismo endpoint que el resto
    # del compose).
    def fake_generate(topic, tone=None, instructions=None):
        return f"Tweet sobre {topic}"

    mocker.patch("app.routers.generate.generate_tweet", side_effect=fake_generate)

    res = client.post("/api/generate/ai/batch", json={"topics": ["gatos", "perros"]})
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["content"] == "Tweet sobre gatos"
    assert "draft_id" not in body[0]
    assert body[0]["error"] is None

    drafts = client.get("/api/tweets?status=draft").json()
    assert len(drafts) == 0


def test_batch_continues_after_one_failure(client, mocker):
    def fake_generate(topic, tone=None, instructions=None):
        if topic == "malo":
            raise AIGenerationError("fallo la generacion")
        return f"Tweet sobre {topic}"

    mocker.patch("app.routers.generate.generate_tweet", side_effect=fake_generate)

    res = client.post("/api/generate/ai/batch", json={"topics": ["bueno", "malo", "otro bueno"]})
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 3
    assert body[0]["error"] is None
    assert body[1]["error"] == "fallo la generacion"
    assert body[1]["content"] is None
    assert body[2]["error"] is None


def test_batch_ignores_blank_lines(client, mocker):
    mocker.patch("app.routers.generate.generate_tweet", return_value="contenido")

    res = client.post("/api/generate/ai/batch", json={"topics": ["tema uno", "  ", "", "tema dos"]})
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_batch_requires_at_least_one_topic(client):
    res = client.post("/api/generate/ai/batch", json={"topics": ["   ", ""]})
    assert res.status_code == 400


def test_batch_rejects_too_many_topics(client):
    res = client.post("/api/generate/ai/batch", json={"topics": [f"tema {i}" for i in range(26)]})
    assert res.status_code == 400
