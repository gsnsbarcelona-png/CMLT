from app.services.x_service import XPublishError


def test_create_and_get_draft(client):
    res = client.post("/api/tweets", json={"content": "hola mundo", "source": "manual"})
    assert res.status_code == 201
    tweet = res.json()
    assert tweet["status"] == "draft"
    assert tweet["char_count"] == len("hola mundo")

    res = client.get(f"/api/tweets/{tweet['id']}")
    assert res.status_code == 200
    assert res.json()["content"] == "hola mundo"


def test_list_filters_by_status(client):
    client.post("/api/tweets", json={"content": "borrador uno", "source": "manual"})
    client.post("/api/tweets", json={"content": "borrador dos", "source": "manual"})

    res = client.get("/api/tweets?status=draft")
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_update_draft(client):
    tweet = client.post("/api/tweets", json={"content": "texto original", "source": "manual"}).json()

    res = client.put(f"/api/tweets/{tweet['id']}", json={"content": "texto editado"})
    assert res.status_code == 200
    assert res.json()["content"] == "texto editado"


def test_delete_draft(client):
    tweet = client.post("/api/tweets", json={"content": "para borrar", "source": "manual"}).json()

    res = client.delete(f"/api/tweets/{tweet['id']}")
    assert res.status_code == 204
    assert client.get(f"/api/tweets/{tweet['id']}").status_code == 404


def test_publish_success(client, mocker):
    mocker.patch("app.routers.tweets.publish_tweet", return_value="98765")
    tweet = client.post("/api/tweets", json={"content": "listo para publicar", "source": "manual"}).json()

    res = client.post(f"/api/tweets/{tweet['id']}/publish")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "published"
    assert body["tweet_id"] == "98765"
    assert body["published_at"] is not None


def test_publish_failure_sets_failed_status(client, mocker):
    mocker.patch("app.routers.tweets.publish_tweet", side_effect=XPublishError("credenciales inválidas"))
    tweet = client.post("/api/tweets", json={"content": "va a fallar", "source": "manual"}).json()

    res = client.post(f"/api/tweets/{tweet['id']}/publish")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failed"
    assert body["error_message"] == "credenciales inválidas"


def test_publish_over_char_limit_rejected(client, mocker):
    publish_mock = mocker.patch("app.routers.tweets.publish_tweet")
    tweet = client.post("/api/tweets", json={"content": "a" * 281, "source": "manual"}).json()

    res = client.post(f"/api/tweets/{tweet['id']}/publish")
    assert res.status_code == 400
    publish_mock.assert_not_called()


def test_retry_after_failure(client, mocker):
    mocker.patch("app.routers.tweets.publish_tweet", side_effect=XPublishError("fallo"))
    tweet = client.post("/api/tweets", json={"content": "va a fallar", "source": "manual"}).json()
    client.post(f"/api/tweets/{tweet['id']}/publish")

    res = client.post(f"/api/tweets/{tweet['id']}/retry")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "draft"
    assert body["error_message"] is None


def test_cannot_publish_twice(client, mocker):
    mocker.patch("app.routers.tweets.publish_tweet", return_value="111")
    tweet = client.post("/api/tweets", json={"content": "único", "source": "manual"}).json()
    client.post(f"/api/tweets/{tweet['id']}/publish")

    res = client.post(f"/api/tweets/{tweet['id']}/publish")
    assert res.status_code == 409


def test_create_draft_with_image_url(client):
    res = client.post(
        "/api/tweets", json={"content": "con imagen", "source": "manual", "image_url": "/data/images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png"}
    )
    assert res.status_code == 201
    assert res.json()["image_url"] == "/data/images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png"


def test_update_draft_image_url(client):
    tweet = client.post("/api/tweets", json={"content": "sin imagen", "source": "manual"}).json()
    assert tweet["image_url"] is None

    res = client.put(
        f"/api/tweets/{tweet['id']}", json={"content": "sin imagen", "image_url": "/data/images/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png"}
    )
    assert res.status_code == 200
    assert res.json()["image_url"] == "/data/images/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png"


def test_publish_passes_image_url_to_publish_tweet(client, mocker):
    publish_mock = mocker.patch("app.routers.tweets.publish_tweet", return_value="1")
    tweet = client.post(
        "/api/tweets", json={"content": "con imagen", "source": "manual", "image_url": "/data/images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png"}
    ).json()

    client.post(f"/api/tweets/{tweet['id']}/publish")

    publish_mock.assert_called_once_with("con imagen", "/data/images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png")
