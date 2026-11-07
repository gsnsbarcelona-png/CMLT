from io import BytesIO

import pytest
from PIL import Image

from app.services import image_service
from app.services.image_service import CANVAS_SIZE, ImageComposeError, compose_branded_image, compose_vs_image


def _fake_logo_bytes(color=(255, 0, 0, 255)) -> bytes:
    img = Image.new("RGBA", (100, 120), color)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def test_compose_vs_image_returns_valid_png_of_expected_size():
    result = compose_vs_image(_fake_logo_bytes((255, 0, 0, 255)), _fake_logo_bytes((0, 0, 255, 255)))

    composed = Image.open(BytesIO(result))
    assert composed.format == "PNG"
    assert composed.size == CANVAS_SIZE


def test_compose_vs_image_invalid_logo_raises():
    with pytest.raises(ImageComposeError):
        compose_vs_image(b"no es una imagen", _fake_logo_bytes())


def test_compose_vs_image_invalid_second_logo_raises():
    with pytest.raises(ImageComposeError):
        compose_vs_image(_fake_logo_bytes(), b"tampoco esto")


def _save_png(img: Image.Image, path) -> None:
    img.save(path, format="PNG")


def _brand_logo_geometry(canvas_w, canvas_h, content_size):
    """Recalcula, con las mismas formulas y constantes que
    compose_branded_image, donde cae el logo de marca -- para poder
    muestrear pixeles alrededor de el sin duplicar numeros magicos."""
    target_h = max(1, int(canvas_h * image_service.BRANDED_LOGO_HEIGHT_RATIO))
    target_w = max(1, int(content_size[0] * (target_h / content_size[1])))
    right_margin = int(canvas_w * image_service.BRANDED_RIGHT_MARGIN_RATIO)
    bottom_margin = int(canvas_h * image_service.BRANDED_BOTTOM_MARGIN_RATIO)
    x = canvas_w - target_w - right_margin
    y = canvas_h - target_h - bottom_margin
    return x, y, target_w, target_h


def test_compose_branded_image_returns_png_matching_background_size(monkeypatch, tmp_path):
    bg_size = (400, 200)
    background = Image.new("RGBA", bg_size, (10, 10, 10, 255))
    background_path = tmp_path / "background.png"
    _save_png(background, background_path)

    # El logo real tiene mucho relleno transparente alrededor del contenido
    # -- se simula aca para probar que compose_branded_image lo recorta antes
    # de escalarlo (si no, el margen invisible cuenta como parte del alto).
    logo = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    content = Image.new("RGBA", (100, 150), (255, 255, 255, 255))
    logo.paste(content, (100, 75))
    logo_path = tmp_path / "logo.png"
    _save_png(logo, logo_path)

    monkeypatch.setattr(image_service, "BRANDING_BACKGROUND_PATH", background_path)
    monkeypatch.setattr(image_service, "BRANDING_LOGO_PATH", logo_path)

    result = compose_branded_image()

    composed = Image.open(BytesIO(result))
    assert composed.format == "PNG"
    assert composed.size == bg_size


def test_compose_branded_image_places_small_logo_bottom_right_with_dark_panel(monkeypatch, tmp_path):
    # El logo es blanco y el fondo puede tener zonas claras -- sin un panel
    # oscuro detras, el logo se pierde. Fondo blanco solido para poder
    # distinguir "panel visible" de "background sin tocar" por color.
    bg_size = (400, 200)
    background = Image.new("RGBA", bg_size, (255, 255, 255, 255))
    background_path = tmp_path / "background.png"
    _save_png(background, background_path)

    content_size = (100, 150)
    logo = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    logo.paste(Image.new("RGBA", content_size, (255, 255, 255, 255)), (100, 75))
    logo_path = tmp_path / "logo.png"
    _save_png(logo, logo_path)

    monkeypatch.setattr(image_service, "BRANDING_BACKGROUND_PATH", background_path)
    monkeypatch.setattr(image_service, "BRANDING_LOGO_PATH", logo_path)

    composed = Image.open(BytesIO(compose_branded_image())).convert("RGB")
    canvas_w, canvas_h = bg_size
    x, y, target_w, target_h = _brand_logo_geometry(canvas_w, canvas_h, content_size)

    # El logo tiene que quedar en la mitad inferior derecha del canvas.
    assert x > canvas_w / 2
    assert y > canvas_h / 2

    # Esquina superior izquierda: lejos del logo y del panel -- sigue blanca
    # (el panel no debe taparlo todo).
    assert composed.getpixel((2, 2)) == (255, 255, 255)

    # Un pixel dentro del padding del panel, justo arriba del logo (fuera
    # del logo mismo) -- debe estar mas oscuro que el fondo blanco.
    padding = int(canvas_h * image_service.BRANDED_PANEL_PADDING_RATIO)
    panel_pixel = composed.getpixel((x + target_w // 2, max(0, y - padding // 2)))
    assert sum(panel_pixel) < sum((255, 255, 255))


def _branding_fixture(monkeypatch, tmp_path, bg_size=(400, 200)):
    background = Image.new("RGBA", bg_size, (10, 10, 10, 255))
    background_path = tmp_path / "background.png"
    _save_png(background, background_path)

    logo = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    logo.paste(Image.new("RGBA", (100, 150), (255, 255, 255, 255)), (100, 75))
    logo_path = tmp_path / "logo.png"
    _save_png(logo, logo_path)

    monkeypatch.setattr(image_service, "BRANDING_BACKGROUND_PATH", background_path)
    monkeypatch.setattr(image_service, "BRANDING_LOGO_PATH", logo_path)


def test_compose_branded_image_single_team_logo_centered(monkeypatch, tmp_path):
    bg_size = (400, 200)
    _branding_fixture(monkeypatch, tmp_path, bg_size)

    team_logo = _fake_logo_bytes((0, 200, 0, 255))
    composed = Image.open(BytesIO(compose_branded_image([team_logo]))).convert("RGB")

    canvas_w, canvas_h = bg_size
    assert composed.getpixel((canvas_w // 2, canvas_h // 2)) == (0, 200, 0)


def test_compose_branded_image_two_team_logos_centered_with_vs_circle(monkeypatch, tmp_path):
    bg_size = (400, 200)
    _branding_fixture(monkeypatch, tmp_path, bg_size)

    team_logo_a = _fake_logo_bytes((0, 200, 0, 255))
    team_logo_b = _fake_logo_bytes((0, 0, 200, 255))
    composed = Image.open(BytesIO(compose_branded_image([team_logo_a, team_logo_b]))).convert("RGB")

    canvas_w, canvas_h = bg_size
    quarter = canvas_w // 4
    center_y = canvas_h // 2

    # Cada escudo centrado en su cuarto correspondiente (izquierda/derecha).
    assert composed.getpixel((quarter, center_y)) == (0, 200, 0)
    assert composed.getpixel((quarter * 3, center_y)) == (0, 0, 200)

    # El circulo "VS" en el medio -- un pixel cerca del borde (lejos del
    # texto, que podria pisar el centro exacto) debe ser el color de relleno.
    radius = int(canvas_h * image_service.BRANDED_VS_CIRCLE_RADIUS_RATIO)
    edge_pixel = composed.getpixel((canvas_w // 2 - radius + 2, center_y))
    assert edge_pixel == tuple(image_service.VS_CIRCLE_COLOR)


def test_compose_branded_image_single_team_logo_has_dark_panel(monkeypatch, tmp_path):
    # Mismo tratamiento que el logo de marca: panel oscuro detras, para que
    # el escudo resalte sobre zonas claras del fondo.
    bg_size = (400, 200)
    background = Image.new("RGBA", bg_size, (255, 255, 255, 255))
    background_path = tmp_path / "background.png"
    _save_png(background, background_path)

    logo = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    logo.paste(Image.new("RGBA", (100, 150), (255, 255, 255, 255)), (100, 75))
    logo_path = tmp_path / "logo.png"
    _save_png(logo, logo_path)

    monkeypatch.setattr(image_service, "BRANDING_BACKGROUND_PATH", background_path)
    monkeypatch.setattr(image_service, "BRANDING_LOGO_PATH", logo_path)

    # Escudo angosto y alto, con relleno transparente alrededor, para que el
    # panel asome por arriba del escudo mismo.
    team_content_size = (40, 200)
    team_logo_img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    team_logo_img.paste(Image.new("RGBA", team_content_size, (0, 200, 0, 255)), (130, 50))
    team_buf = BytesIO()
    team_logo_img.save(team_buf, format="PNG")
    team_logo_bytes = team_buf.getvalue()

    composed = Image.open(BytesIO(compose_branded_image([team_logo_bytes]))).convert("RGB")
    canvas_w, canvas_h = bg_size

    # Misma transformacion que compose_branded_image (recorte + contain-fit)
    # para saber el alto real ya escalado, sin duplicar el redondeo interno
    # de Image.thumbnail.
    team_box = int(canvas_h * image_service.BRANDED_TEAM_LOGO_BOX_RATIO)
    fitted = image_service._fit_contain(
        image_service._crop_to_content(Image.open(BytesIO(team_logo_bytes)).convert("RGBA")), team_box
    )
    y = canvas_h // 2 - fitted.height // 2
    padding = int(canvas_h * image_service.BRANDED_PANEL_PADDING_RATIO)

    panel_pixel = composed.getpixel((canvas_w // 2, max(0, y - padding // 2)))
    assert sum(panel_pixel) < sum((255, 255, 255))


def test_compose_branded_image_two_team_logos_share_one_rectangular_panel(monkeypatch, tmp_path):
    # Escudo A mucho mas alto que B (llena el team_box entero en alto) -- si
    # el panel fuera uno por escudo, arriba de B seguiria mostrando el fondo
    # blanco; con un solo rectangulo compartido (tan alto como el mas alto
    # de los dos), arriba de B tambien queda tapado por el panel.
    bg_size = (400, 200)
    background = Image.new("RGBA", bg_size, (255, 255, 255, 255))
    background_path = tmp_path / "background.png"
    _save_png(background, background_path)

    logo = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    logo.paste(Image.new("RGBA", (100, 150), (255, 255, 255, 255)), (100, 75))
    logo_path = tmp_path / "logo.png"
    _save_png(logo, logo_path)

    monkeypatch.setattr(image_service, "BRANDING_BACKGROUND_PATH", background_path)
    monkeypatch.setattr(image_service, "BRANDING_LOGO_PATH", logo_path)

    def _team_logo_bytes(content_h):
        img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        img.paste(Image.new("RGBA", (100, content_h), (0, 200, 0, 255)), (100, 150 - content_h // 2))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    team_logo_a = _team_logo_bytes(260)  # alto: ocupa casi todo el team_box
    team_logo_b = _team_logo_bytes(40)  # bajo

    composed = Image.open(BytesIO(compose_branded_image([team_logo_a, team_logo_b]))).convert("RGB")
    canvas_w, canvas_h = bg_size
    quarter = canvas_w // 4

    team_box = int(canvas_h * image_service.BRANDED_TEAM_LOGO_BOX_RATIO)
    fitted_b = image_service._fit_contain(
        image_service._crop_to_content(Image.open(BytesIO(team_logo_b)).convert("RGBA")), team_box
    )
    y_b_top = canvas_h // 2 - fitted_b.height // 2

    # Justo arriba del escudo B (mas bajo), en su misma columna -- debe estar
    # tapado por el panel compartido (mas oscuro que el fondo blanco), no
    # mostrar el fondo blanco sin tocar.
    sample_pixel = composed.getpixel((quarter * 3, max(0, y_b_top - 5)))
    assert sum(sample_pixel) < sum((255, 255, 255))


def test_compose_branded_image_missing_files_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(image_service, "BRANDING_BACKGROUND_PATH", tmp_path / "no_existe.png")
    monkeypatch.setattr(image_service, "BRANDING_LOGO_PATH", tmp_path / "tampoco.png")

    with pytest.raises(ImageComposeError):
        compose_branded_image()


def test_compose_branded_image_invalid_team_logo_raises(monkeypatch, tmp_path):
    background = Image.new("RGBA", (400, 200), (10, 10, 10, 255))
    background_path = tmp_path / "background.png"
    _save_png(background, background_path)
    logo = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    logo_path = tmp_path / "logo.png"
    _save_png(logo, logo_path)

    monkeypatch.setattr(image_service, "BRANDING_BACKGROUND_PATH", background_path)
    monkeypatch.setattr(image_service, "BRANDING_LOGO_PATH", logo_path)

    with pytest.raises(ImageComposeError):
        compose_branded_image([b"no es una imagen"])
