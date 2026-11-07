"""Config activa por split (torneos/temporada) con autodescubrimiento."""
import logging
import re
import time

import httpx

from app.config import settings
from app.services.golgg.client import GOLGG_BASE, GOLGG_HEADERS
from app.services.golgg.models import ActiveConfig, GolGGError

logger = logging.getLogger(__name__)


def discover_tournaments(season: str | None = None, region: str | None = "ES") -> list[dict]:
    """Lista los torneos disponibles en gol.gg para una temporada (por defecto
    la configurada) y region (por defecto ES). Pega directo al endpoint AJAX
    que usa la propia pagina https://gol.gg/tournament/list/ (descubierto
    inspeccionando su JS) -- pensado como herramienta de mantenimiento para
    encontrar el nombre exacto de un torneo nuevo en cada split, sin tener
    que buscarlo a mano. No pasa por la cache de _cached_get (es un POST,
    y es una consulta ocasional de mantenimiento, no parte del flujo normal
    de generacion)."""
    season = season or get_active_config().season
    try:
        response = httpx.post(
            f"{GOLGG_BASE}/tournament/ajax.trlist.php",
            data={"season": season},
            headers=GOLGG_HEADERS,
            timeout=10.0,
        )
        response.raise_for_status()
        tournaments = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GolGGError("No se pudo consultar el listado de torneos de gol.gg.") from exc

    if region:
        tournaments = [t for t in tournaments if t.get("region") == region]
    return tournaments


_ACTIVE_CONFIG_TTL_SECONDS = 6 * 3600
_ACTIVE_CONFIG_RETRY_SECONDS = 300
_active_config_cache: tuple[float, ActiveConfig] | None = None
_active_config_failed_at: float | None = None


def _split_csv(value: str) -> list[str]:
    return [t.strip() for t in value.split(",") if t.strip()]


def _config_from_settings() -> ActiveConfig:
    return ActiveConfig(
        season=settings.golgg_season,
        tournament=settings.golgg_tournament,
        year_tournaments=_split_csv(settings.golgg_year_tournaments),
        lec_tournament=settings.lec_tournament,
        emea_masters_tournaments=_split_csv(settings.emea_masters_tournaments),
    )


def _season_number(season: str) -> int | None:
    match = re.fullmatch(r"S(\d+)", season.strip())
    return int(match.group(1)) if match else None


def _is_les(tournament: dict) -> bool:
    return tournament.get("region") == "ES" and tournament.get("trname", "").startswith("LES ")


def _discover_active_config() -> ActiveConfig:
    """Arma la config activa a partir del listado real de gol.gg: la temporada
    mas nueva con torneos de LES, el ultimo torneo regular de LES, todos los
    de LES de esa temporada (incluye Final Four/playoffs), el ultimo LEC
    regular y todos los EMEA Masters. Levanta GolGGError si no hay LES."""
    base = _config_from_settings()
    season = base.season
    number = _season_number(season)
    tournaments = discover_tournaments(season, region=None)
    while number is not None:
        next_season = f"S{number + 1}"
        next_tournaments = discover_tournaments(next_season, region=None)
        if not any(_is_les(t) for t in next_tournaments):
            break
        season, number, tournaments = next_season, number + 1, next_tournaments

    def by_start(items: list[dict]) -> list[dict]:
        return sorted(items, key=lambda t: t.get("firstgame", ""))

    les = by_start([t for t in tournaments if _is_les(t)])
    if not les:
        raise GolGGError(f"gol.gg no lista torneos de LES para la temporada {season}.")
    regular = [t for t in les if not re.search(r"playoffs|final four", t["trname"], re.I)] or les
    lec = by_start(
        [t for t in tournaments if t.get("trname", "").startswith("LEC ") and "Season" in t.get("trname", "")]
    )
    emea = by_start([t for t in tournaments if "EMEA Masters" in t.get("trname", "")])
    return ActiveConfig(
        season=season,
        tournament=regular[-1]["trname"],
        year_tournaments=[t["trname"] for t in les],
        lec_tournament=lec[-1]["trname"] if lec else base.lec_tournament,
        emea_masters_tournaments=[t["trname"] for t in emea] or base.emea_masters_tournaments,
    )


def get_active_config() -> ActiveConfig:
    global _active_config_cache, _active_config_failed_at
    if not settings.golgg_autodiscover:
        return _config_from_settings()
    now = time.monotonic()
    if _active_config_cache is not None and now - _active_config_cache[0] < _ACTIVE_CONFIG_TTL_SECONDS:
        return _active_config_cache[1]
    fallback = _active_config_cache[1] if _active_config_cache else _config_from_settings()
    if _active_config_failed_at is not None and now - _active_config_failed_at < _ACTIVE_CONFIG_RETRY_SECONDS:
        return fallback
    try:
        config = _discover_active_config()
    except GolGGError as exc:
        _active_config_failed_at = now
        logger.warning("Autodescubrimiento de torneos fallo, se usa la config anterior/del .env: %s", exc)
        return fallback
    _active_config_failed_at = None
    _active_config_cache = (now, config)
    logger.info("Config gol.gg descubierta: %s", config)
    return config


def reset_active_config_cache() -> None:
    global _active_config_cache, _active_config_failed_at
    _active_config_cache = None
    _active_config_failed_at = None


def get_year_tournaments() -> list[str]:
    return get_active_config().year_tournaments


def get_lec_tournament() -> str:
    return get_active_config().lec_tournament


def get_emea_masters_tournaments() -> list[str]:
    return get_active_config().emea_masters_tournaments


def get_current_tournament() -> str:
    return get_active_config().tournament
