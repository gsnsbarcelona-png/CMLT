"""Validacion de `image_url` (la guarda cada Tweet y se lee/descarga al
publicar en X). Solo se aceptan dos formas: una imagen propia subida/generada
por la app ("/data/images/<uuid>.<ext>") o el escudo de un equipo servido por
lolesports. Cualquier otra cosa (rutas relativas, "../.env", hosts internos)
se rechaza, para que no se pueda hacer leer archivos del servidor ni pedirle
que descargue URLs arbitrarias."""

import re
from urllib.parse import urlparse

LOCAL_IMAGE_RE = re.compile(r"^/data/images/[0-9a-f]{32}\.(png|jpg|jpeg|gif|webp)$")
ALLOWED_REMOTE_HOST_SUFFIXES = ("lolesports.com", "akamaihd.net")


def is_allowed_image_url(url: str) -> bool:
    if LOCAL_IMAGE_RE.fullmatch(url):
        return True
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in ("http", "https") and any(
        host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_REMOTE_HOST_SUFFIXES
    )


def validate_image_url(url: str | None) -> str | None:
    if url is None or url == "":
        return None
    if not is_allowed_image_url(url):
        raise ValueError("image_url no valida: solo imagenes propias (/data/images/...) o escudos de lolesports.")
    return url
