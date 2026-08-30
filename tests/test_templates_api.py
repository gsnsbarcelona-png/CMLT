def test_create_and_list_templates(client):
    res = client.post(
        "/api/templates",
        json={"name": "Anuncio", "template_text": "Lanzamos {producto} el {fecha}!"},
    )
    assert res.status_code == 201
    template = res.json()
    assert template["name"] == "Anuncio"

    res = client.get("/api/templates")
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_update_and_delete_template(client):
    template = client.post(
        "/api/templates", json={"name": "Original", "template_text": "hola {nombre}"}
    ).json()

    res = client.put(
        f"/api/templates/{template['id']}",
        json={"name": "Editado", "template_text": "chau {nombre}"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Editado"

    res = client.delete(f"/api/templates/{template['id']}")
    assert res.status_code == 204
    assert client.get(f"/api/templates/{template['id']}").status_code == 404


def test_render_from_template_success(client):
    template = client.post(
        "/api/templates", json={"name": "Producto", "template_text": "Lanzamos {producto}!"}
    ).json()

    res = client.post(
        "/api/generate/template",
        json={"template_id": template["id"], "variables": {"producto": "Widget X"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["content"] == "Lanzamos Widget X!"
    assert body["within_limit"] is True


def test_render_from_template_missing_variable(client):
    template = client.post(
        "/api/templates", json={"name": "Producto", "template_text": "Lanzamos {producto}!"}
    ).json()

    res = client.post("/api/generate/template", json={"template_id": template["id"], "variables": {}})
    assert res.status_code == 400


def test_render_from_missing_template(client):
    res = client.post("/api/generate/template", json={"template_id": 9999, "variables": {}})
    assert res.status_code == 404
