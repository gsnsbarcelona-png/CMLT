"""Cliente HTTP de gol.gg: cache en memoria con TTL, reintentos, copia
caducada si gol.gg cae, precalentamiento en paralelo y parseo de tablas."""
import functools
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from bs4 import BeautifulSoup

from app.services.golgg.models import GolGGError

logger = logging.getLogger(__name__)


GOLGG_BASE = "https://gol.gg"
# gol.gg devuelve 403 con el User-Agent default de httpx -> hace falta uno de navegador.
GOLGG_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# gol.gg no cambia segundo a segundo, y una sola generacion de Stats con
# "equipos" ya pega varias veces a las mismas paginas (compute_head_to_head_candidates
# recorre los mismos torneos que aggregate_team_stats, y el usuario suele
# generar varias veces seguidas mientras prueba/edita). Una cache corta en
# memoria evita repetir esos pedidos sin arriesgar datos muy desactualizados.
_CACHE_TTL_SECONDS = 900
_MAX_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 1.0
_http_cache: dict[str, tuple[float, str]] = {}


def _cached_get(url: str) -> str:
    cached = _http_cache.get(url)
    now = time.monotonic()
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    last_error: Exception | None = None
    message = "No se pudo obtener las estadísticas de gol.gg. Intenta de nuevo en unos minutos."
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = httpx.get(url, headers=GOLGG_HEADERS, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status = exc.response.status_code
            logger.warning("gol.gg %s en %s (intento %d/%d)", status, url, attempt + 1, _MAX_ATTEMPTS)
            if status in (403, 429):
                message = "gol.gg nos está limitando las peticiones. Espera unos minutos y vuelve a probar."
            if status not in (429, 500, 502, 503, 504):
                break  # 403/404...: reintentar no ayuda
        except httpx.HTTPError as exc:
            last_error = exc
            logger.warning("gol.gg fallo de red en %s (intento %d/%d): %s", url, attempt + 1, _MAX_ATTEMPTS, exc)
        else:
            _http_cache[url] = (now, response.text)
            return response.text
        if attempt + 1 < _MAX_ATTEMPTS:
            time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))

    # Si gol.gg falla pero hay una copia caducada, mejor datos algo viejos
    # que un error (los stats cambian por partido, no por minuto).
    if cached is not None:
        logger.warning("gol.gg caído: se usa la copia cacheada (%.0f s de antigüedad) de %s", now - cached[0], url)
        return cached[1]
    raise GolGGError(message) from last_error


@functools.lru_cache(maxsize=64)
def _parse_table(html: str, table_class: str):
    """Parsear una pagina de gol.gg con BeautifulSoup es CPU pura y se
    repetia en cada llamada aunque el HTML ya estuviera cacheado. El mismo
    string de HTML (misma identidad, viene de _http_cache) reutiliza el
    resultado. Solo se lee la tabla, nunca se modifica."""
    return BeautifulSoup(html, "html.parser").find("table", class_=table_class)


def _fetch_table(url: str, table_class: str) -> BeautifulSoup:
    table = _parse_table(_cached_get(url), table_class)
    if table is None:
        raise GolGGError("gol.gg devolvió una página sin la tabla de estadísticas esperada.")
    return table


_PREFETCH_WORKERS = 6


def warm_urls(urls: list[str]) -> None:
    """Descarga varias paginas de gol.gg EN PARALELO para llenar la cache; el
    codigo secuencial de despues las encuentra ya cacheadas. Los errores se
    ignoran aqui a proposito: reaparecen (con reintentos y copia cacheada) en
    la llamada normal, que es la que sabe como degradar."""
    unique = list(dict.fromkeys(urls))
    if len(unique) < 2:
        return

    def _safe(url: str) -> None:
        try:
            _cached_get(url)
        except GolGGError:
            pass

    with ThreadPoolExecutor(max_workers=min(_PREFETCH_WORKERS, len(unique))) as pool:
        list(pool.map(_safe, unique))


_real_warm_urls = warm_urls  # los tests parchean warm_urls (sin red) y usan esta para probarla
