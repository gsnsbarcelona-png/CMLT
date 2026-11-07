import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

CANVAS_SIZE = (640, 320)
LOGO_BOX = 260  # cada escudo entra en un cuadrado de este lado (contain, sin deformar)
BACKGROUND_COLOR = (17, 24, 39)  # slate-900, oscuro para que resalten escudos claros u oscuros
VS_CIRCLE_COLOR = (220, 38, 38)  # rojo, convención visual de "VS"
VS_CIRCLE_RADIUS = 55
VS_TEXT_COLOR = (255, 255, 255)

# Fondo de marca del programa: dos archivos estaticos (no dependen de ningun
# dato de un tweet puntual) provistos por el usuario -- ver README, seccion
# "Fondo de marca".
BRANDING_DIR = Path(__file__).resolve().parent.parent / "data" / "branding"
BRANDING_BACKGROUND_PATH = BRANDING_DIR / "background.png"
BRANDING_LOGO_PATH = BRANDING_DIR / "logo.png"
BRANDED_LOGO_HEIGHT_RATIO = 0.15  # el logo de marca es chico, abajo a la derecha
BRANDED_RIGHT_MARGIN_RATIO = 0.05  # margen derecho del logo de marca, relativo al ancho del fondo
BRANDED_BOTTOM_MARGIN_RATIO = 0.06  # margen inferior del logo de marca, relativo al alto del fondo
BRANDED_PANEL_COLOR = (8, 8, 8)  # casi negro, detrás del logo de marca para que resalte sobre fondos claros
BRANDED_PANEL_ALPHA = 145  # ~57% de opacidad -- deja intuir el fondo detrás, no lo tapa del todo
BRANDED_PANEL_PADDING_RATIO = 0.055  # relativo al alto del fondo
BRANDED_PANEL_RADIUS_RATIO = 0.02  # relativo al alto del fondo
BRANDED_TEAM_LOGO_BOX_RATIO = 0.42  # el/los escudo(s) de equipo, centrados, entran en un cuadrado de este lado (relativo al alto)
BRANDED_VS_CIRCLE_RADIUS_RATIO = 0.09  # relativo al alto del fondo
BRANDED_VS_FONT_RATIO = 0.075  # relativo al alto del fondo

# Candidatos de fuente en negrita -- Arial Bold (Windows) primero, con
# fallbacks razonables; si ninguno esta disponible se usa la fuente por
# defecto de Pillow (mas fea, pero nunca rompe la generacion del composite).
_BOLD_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


class ImageComposeError(Exception):
    pass


# --- Cache en memoria de escudos descargados (bytes por URL) ---------------
LOGO_CACHE_TTL_SECONDS = 3600
LOGO_CACHE_MAX_ENTRIES = 64
_logo_cache: dict[str, tuple[float, bytes]] = {}
_logo_cache_lock = threading.Lock()


def clear_logo_cache() -> None:
    with _logo_cache_lock:
        _logo_cache.clear()


def fetch_logo_bytes(url: str) -> bytes:
    """Bytes del escudo en `url`, con cache en memoria (TTL + tope de
    entradas). Levanta httpx.HTTPError si la descarga falla."""
    now = time.monotonic()
    with _logo_cache_lock:
        hit = _logo_cache.get(url)
        if hit and now - hit[0] < LOGO_CACHE_TTL_SECONDS:
            return hit[1]
    response = httpx.get(url, timeout=10.0, follow_redirects=True)
    response.raise_for_status()
    data = response.content
    with _logo_cache_lock:
        if len(_logo_cache) >= LOGO_CACHE_MAX_ENTRIES:
            for key in [k for k, (ts, _) in _logo_cache.items() if now - ts >= LOGO_CACHE_TTL_SECONDS]:
                del _logo_cache[key]
            while len(_logo_cache) >= LOGO_CACHE_MAX_ENTRIES:
                del _logo_cache[min(_logo_cache, key=lambda k: _logo_cache[k][0])]
        _logo_cache[url] = (now, data)
    return data


def fetch_logos_parallel(urls: list[str]) -> list[bytes | Exception]:
    """Descarga los escudos en paralelo; devuelve, por URL y en orden, los
    bytes o la excepcion httpx.HTTPError que fallo (no levanta)."""
    def _one(url: str) -> bytes | Exception:
        try:
            return fetch_logo_bytes(url)
        except httpx.HTTPError as exc:
            return exc

    if len(urls) <= 1:
        return [_one(u) for u in urls]
    with ThreadPoolExecutor(max_workers=len(urls)) as pool:
        return list(pool.map(_one, urls))


IMAGE_RENDER_VERSION = "1"  # subir si cambia el diseño, para no reutilizar PNGs viejos


def deterministic_image_name(kind: str, *parts: str) -> str:
    """Nombre de archivo estable (sha1 -> 32 hex minusculas + .png) para una
    imagen compuesta; cumple image_urls.LOCAL_IMAGE_RE."""
    raw = "|".join([IMAGE_RENDER_VERSION, kind, *parts])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:32] + ".png"


# --- Imagenes de marca: se cargan una vez (por ruta y mtime) ----------------
_branding_cache: dict[tuple[str, int], Image.Image] = {}
_branding_lock = threading.Lock()


def _load_branding(path: Path) -> Image.Image:
    key = (str(path), path.stat().st_mtime_ns)
    with _branding_lock:
        img = _branding_cache.get(key)
        if img is None:
            img = Image.open(path).convert("RGBA")
            for old in [k for k in _branding_cache if k[0] == key[0]]:
                del _branding_cache[old]
            _branding_cache[key] = img
    return img.copy()


def _load_bold_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _BOLD_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _open_rgba(data: bytes, error_message: str) -> Image.Image:
    try:
        return Image.open(BytesIO(data)).convert("RGBA")
    except Exception as exc:  # Pillow puede levantar varios tipos según el formato inválido
        raise ImageComposeError(error_message) from exc


def _fit_contain(img: Image.Image, box: int) -> Image.Image:
    """Encoge `img` (sin deformar) para que entre en un cuadrado de lado
    `box` -- se usa para escudos, que pueden ser mas anchos que altos o
    viceversa segun el equipo."""
    img = img.copy()
    img.thumbnail((box, box), Image.LANCZOS)
    return img


def _fit_logo(logo_bytes: bytes) -> Image.Image:
    logo = _open_rgba(logo_bytes, "No se pudo leer uno de los escudos como imagen.")
    return _fit_contain(logo, LOGO_BOX)


def compose_vs_image(logo_a_bytes: bytes, logo_b_bytes: bytes) -> bytes:
    """Arma un composite "EquipoA VS EquipoB": los dos escudos lado a lado
    sobre un fondo oscuro, con un circulo rojo "VS" superpuesto en el medio.
    Devuelve bytes PNG listos para guardar/subir."""
    logo_a = _fit_logo(logo_a_bytes)
    logo_b = _fit_logo(logo_b_bytes)

    canvas = Image.new("RGBA", CANVAS_SIZE, (*BACKGROUND_COLOR, 255))

    quarter = CANVAS_SIZE[0] // 4
    center_y = CANVAS_SIZE[1] // 2
    for logo, center_x in ((logo_a, quarter), (logo_b, quarter * 3)):
        pos = (center_x - logo.width // 2, center_y - logo.height // 2)
        canvas.alpha_composite(logo, pos)

    draw = ImageDraw.Draw(canvas)
    cx, cy = CANVAS_SIZE[0] // 2, CANVAS_SIZE[1] // 2
    draw.ellipse(
        (cx - VS_CIRCLE_RADIUS, cy - VS_CIRCLE_RADIUS, cx + VS_CIRCLE_RADIUS, cy + VS_CIRCLE_RADIUS),
        fill=VS_CIRCLE_COLOR,
    )
    font = _load_bold_font(44)
    text = "VS"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - text_w / 2 - bbox[0], cy - text_h / 2 - bbox[1]), text, fill=VS_TEXT_COLOR, font=font)

    buffer = BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _crop_to_content(img: Image.Image) -> Image.Image:
    """La mayoria de estos PNG (logo de marca, escudos de equipo) tienen
    relleno transparente alrededor del contenido real -- sin recortarlo, ese
    margen invisible cuenta como parte del alto al escalar y el resultado
    queda mas chico de lo esperado."""
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def _fit_height(img: Image.Image, target_h: int) -> Image.Image:
    target_h = max(1, target_h)
    scale = target_h / img.height
    target_w = max(1, int(img.width * scale))
    return img.resize((target_w, target_h), Image.LANCZOS)


def _draw_panel(canvas: Image.Image, box: tuple[int, int, int, int], padding: int) -> None:
    """Panel semitransparente oscuro con esquinas redondeadas detras de un
    logo/escudo, para que resalte sobre zonas claras del fondo -- mismo
    tratamiento para el logo de marca y para cada escudo de equipo."""
    canvas_w, canvas_h = canvas.size
    padded_box = (
        max(0, box[0] - padding),
        max(0, box[1] - padding),
        min(canvas_w, box[2] + padding),
        min(canvas_h, box[3] + padding),
    )
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(
        padded_box,
        radius=int(canvas_h * BRANDED_PANEL_RADIUS_RATIO),
        fill=(*BRANDED_PANEL_COLOR, BRANDED_PANEL_ALPHA),
    )
    canvas.alpha_composite(overlay)


def compose_branded_image(team_logo_bytes_list: list[bytes] | None = None) -> bytes:
    """Fondo de marca del programa (background.png) con el isotipo (logo.png,
    PNG con fondo transparente) chico, pegado abajo a la derecha, sobre un
    panel semitransparente oscuro (el logo es blanco y el fondo tiene zonas
    claras, sin el panel se pierde ahi). Si se pasa un escudo de equipo, va
    centrado en el medio del fondo, con el mismo panel detras; si se pasan
    dos (H2H/Duelo), van centrados a los lados sobre un unico panel
    rectangular compartido, con un circulo "VS" en el medio (igual que
    compose_vs_image pero sobre el fondo de marca). Devuelve bytes PNG."""
    try:
        background = _load_branding(BRANDING_BACKGROUND_PATH)
        brand_logo = _load_branding(BRANDING_LOGO_PATH)
    except Exception as exc:  # archivo faltante o imagen inválida
        raise ImageComposeError("No se pudo generar la imagen de marca (falta el fondo o el logo).") from exc

    canvas = background
    canvas_w, canvas_h = canvas.size
    center_y = canvas_h // 2
    padding = int(canvas_h * BRANDED_PANEL_PADDING_RATIO)

    def _place_with_panel(logo: Image.Image, cx: int, cy: int) -> None:
        pos = (cx - logo.width // 2, cy - logo.height // 2)
        box = (pos[0], pos[1], pos[0] + logo.width, pos[1] + logo.height)
        _draw_panel(canvas, box, padding)
        canvas.alpha_composite(logo, pos)

    team_box = int(canvas_h * BRANDED_TEAM_LOGO_BOX_RATIO)
    team_logos = [
        _fit_contain(
            _crop_to_content(_open_rgba(data, "No se pudo leer uno de los escudos de equipo como imagen.")),
            team_box,
        )
        for data in (team_logo_bytes_list or [])
    ]

    if len(team_logos) == 1:
        _place_with_panel(team_logos[0], canvas_w // 2, center_y)
    elif len(team_logos) >= 2:
        # Un solo panel rectangular para los dos escudos (y el circulo "VS"
        # que va encima, entre ellos) en vez de un cuadrado por escudo.
        quarter = canvas_w // 4
        placements = [
            (logo, (cx - logo.width // 2, center_y - logo.height // 2))
            for logo, cx in ((team_logos[0], quarter), (team_logos[1], quarter * 3))
        ]
        combined_box = (
            min(pos[0] for _, pos in placements),
            min(pos[1] for _, pos in placements),
            max(pos[0] + logo.width for logo, pos in placements),
            max(pos[1] + logo.height for logo, pos in placements),
        )
        _draw_panel(canvas, combined_box, padding)
        for logo, pos in placements:
            canvas.alpha_composite(logo, pos)

        draw = ImageDraw.Draw(canvas)
        cx = canvas_w // 2
        radius = int(canvas_h * BRANDED_VS_CIRCLE_RADIUS_RATIO)
        draw.ellipse((cx - radius, center_y - radius, cx + radius, center_y + radius), fill=VS_CIRCLE_COLOR)
        font = _load_bold_font(int(canvas_h * BRANDED_VS_FONT_RATIO))
        text = "VS"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (cx - text_w / 2 - bbox[0], center_y - text_h / 2 - bbox[1]), text, fill=VS_TEXT_COLOR, font=font
        )

    brand_logo = _fit_height(_crop_to_content(brand_logo), int(canvas_h * BRANDED_LOGO_HEIGHT_RATIO))
    right_margin = int(canvas_w * BRANDED_RIGHT_MARGIN_RATIO)
    bottom_margin = int(canvas_h * BRANDED_BOTTOM_MARGIN_RATIO)
    brand_x = canvas_w - brand_logo.width - right_margin
    brand_y = canvas_h - brand_logo.height - bottom_margin
    _place_with_panel(brand_logo, brand_x + brand_logo.width // 2, brand_y + brand_logo.height // 2)

    buffer = BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()
