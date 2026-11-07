"""Tarjetas de imagen (PNG 1200x675, formato 16:9 que X muestra sin recortar)
dibujadas con Pillow: Resultados de la jornada y Top 3. Sin red ni IA: solo
pintan los datos que ya se generaron. Estilo sobrio: fondo oscuro, acento azul."""

import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 675
BG = (15, 20, 25)
PANEL = (24, 32, 41)
PANEL_ALT = (30, 40, 51)
ACCENT = (29, 155, 240)  # #1d9bf0
TEXT = (231, 233, 234)
MUTED = (139, 152, 165)
MARGIN = 56

# DejaVu primero (Linux/Render), luego fuentes de Windows; si no hay ninguna,
# ImageFont.load_default(size=...) (Pillow >= 10.1).
_REGULAR_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_BOLD_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _font(bold: bool, size: int) -> ImageFont.ImageFont:
    for path in _BOLD_FONTS if bold else _REGULAR_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow antiguo: sin parametro de tamano
        return ImageFont.load_default()


def _width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    return draw.textlength(text, font=font)


def _fit(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> str:
    """Recorta con puntos suspensivos para que el texto nunca desborde."""
    if _width(draw, text, font) <= max_width:
        return text
    while text and _width(draw, text + "…", font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _text_at(draw, xy, text, font, fill, anchor="lm"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def _base(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 10, HEIGHT), fill=ACCENT)
    title_font = _font(True, 46)
    draw.text((MARGIN, 40), _fit(draw, title, title_font, WIDTH - 2 * MARGIN), font=title_font, fill=TEXT)
    if subtitle:
        sub_font = _font(False, 26)
        draw.text((MARGIN, 100), _fit(draw, subtitle, sub_font, WIDTH - 2 * MARGIN), font=sub_font, fill=ACCENT)
    return img, draw


def _png(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_results_card(title: str, subtitle: str, matches: list[dict]) -> bytes:
    """matches: dicts con team1, score1, team2, score2 y opcional block.
    El ganador (mayor marcador) se resalta en azul y negrita."""
    img, draw = _base(title, subtitle)
    top, bottom = 150, HEIGHT - 44
    n = max(len(matches), 1)
    gap = 6
    row_h = min(78, (bottom - top - gap * (n - 1)) // n)
    size = max(16, min(34, int(row_h * 0.52)))
    f_reg, f_bold = _font(False, size), _font(True, size)
    f_small = _font(False, max(13, int(size * 0.62)))
    left, right = MARGIN, WIDTH - MARGIN
    mid = (left + right) // 2
    score_w = 150
    team_max = (right - left) / 2 - score_w / 2 - 34

    for i, m in enumerate(matches):
        y0 = top + i * (row_h + gap)
        y1 = y0 + row_h
        draw.rounded_rectangle((left, y0, right, y1), radius=10, fill=PANEL if i % 2 == 0 else PANEL_ALT)
        cy = (y0 + y1) // 2
        s1, s2 = int(m["score1"]), int(m["score2"])
        win1, win2 = s1 > s2, s2 > s1
        for side, name, win in ((1, m["team1"], win1), (2, m["team2"], win2)):
            font = f_bold if win else f_reg
            color = ACCENT if win else TEXT
            label = _fit(draw, name, font, team_max)
            if side == 1:
                _text_at(draw, (mid - score_w // 2 - 20, cy), label, font, color, "rm")
            else:
                _text_at(draw, (mid + score_w // 2 + 20, cy), label, font, color, "lm")
        _text_at(draw, (mid - 38, cy), str(s1), f_bold, ACCENT if win1 else MUTED, "mm")
        _text_at(draw, (mid, cy), "-", f_reg, MUTED, "mm")
        _text_at(draw, (mid + 38, cy), str(s2), f_bold, ACCENT if win2 else MUTED, "mm")
        if m.get("block"):
            block = _fit(draw, m["block"], f_small, 130)
            _text_at(draw, (left + 16, cy), block, f_small, MUTED, "lm")

    draw.text((MARGIN, HEIGHT - 34), "Tweet Automation · LES", font=_font(False, 20), fill=MUTED)
    return _png(img)


def render_top_card(title: str, subtitle: str, unit: str, entries: list[dict]) -> bytes:
    """entries: dicts con name y value (texto ya formateado), mejor primero."""
    img, draw = _base(title, subtitle)
    top, bottom = 160, HEIGHT - 60
    n = max(len(entries), 1)
    gap = 10
    row_h = min(130, (bottom - top - gap * (n - 1)) // n)
    size = max(18, min(48, int(row_h * 0.42)))
    f_bold = _font(True, size)
    f_unit = _font(False, max(14, int(size * 0.5)))
    left, right = MARGIN, WIDTH - MARGIN

    for i, e in enumerate(entries):
        y0 = top + i * (row_h + gap)
        y1 = y0 + row_h
        cy = (y0 + y1) // 2
        first = i == 0
        draw.rounded_rectangle((left, y0, right, y1), radius=12, fill=PANEL_ALT if first else PANEL)
        if first:
            draw.rounded_rectangle((left, y0, left + 8, y1), radius=4, fill=ACCENT)
        _text_at(draw, (left + 50, cy), f"{i + 1}", f_bold, ACCENT if first else MUTED, "mm")
        value = str(e["value"])
        val_w = _width(draw, value, f_bold)
        unit_w = _width(draw, unit, f_unit) + 14 if unit else 0
        _text_at(draw, (right - 28, cy), value, f_bold, ACCENT if first else TEXT, "rm")
        if unit:
            _text_at(draw, (right - 28 - val_w - 14, cy), unit, f_unit, MUTED, "rm")
        name = _fit(draw, e["name"], f_bold, right - left - 100 - val_w - unit_w - 60)
        _text_at(draw, (left + 100, cy), name, f_bold, TEXT, "lm")

    draw.text((MARGIN, HEIGHT - 40), "Tweet Automation · LES", font=_font(False, 20), fill=MUTED)
    return _png(img)


def save_card(png: bytes, images_dir: Path) -> str:
    """Guarda el PNG igual que las subidas de /api/images (uuid4 hex)."""
    images_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    (images_dir / filename).write_bytes(png)
    return f"/data/images/{filename}"
