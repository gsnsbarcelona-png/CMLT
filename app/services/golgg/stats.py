"""Descarga y parseo de las tablas de equipos/jugadores de gol.gg y su agregado."""
import logging

from bs4 import BeautifulSoup

from app.services.golgg import client
from app.services.golgg.client import GOLGG_BASE, _fetch_table
from app.services.golgg.config import get_active_config
from app.services.golgg.models import GolGGError, PlayerStat, TeamStat

logger = logging.getLogger(__name__)


def _tournament_path(prefix: str, tournament: str | None = None) -> str:
    config = get_active_config()
    tournament = tournament or config.tournament
    # "ALL" funciona para el segmento split en todos los torneos probados
    # (regular season Y playoffs), a diferencia de inferir el split del nombre
    # del torneo -- confirmado en vivo: para "LES 2026 Summer Playoffs" el
    # listado de equipos necesita split-Playoffs pero el de jugadores
    # split-Summer/ALL (gol.gg es inconsistente entre sus propias paginas).
    # "ALL" evita tener que adivinar cual de los dos hace falta en cada caso.
    return (
        f"{GOLGG_BASE}/{prefix}/list/season-{config.season}/"
        f"split-ALL/tournament-{tournament}/"
    )


def warm_stats_pages(team_tournaments: list[str | None] = (), player_tournaments: list[str | None] = ()) -> None:
    """Calienta en paralelo las tablas de equipos/jugadores de esos torneos
    (None = el torneo actual)."""
    client.warm_urls(
        [_tournament_path("teams", t) for t in team_tournaments]
        + [_tournament_path("players", t) for t in player_tournaments]
    )


def prewarm() -> None:
    """Se lanza en segundo plano al arrancar (Render tarda en despertar y el
    primer clic pagaba todas las descargas): descubre la config y calienta las
    paginas mas usadas. Nunca levanta."""
    try:
        config = get_active_config()
        warm_stats_pages(
            team_tournaments=[None, config.lec_tournament],
            player_tournaments=[None, config.lec_tournament],
        )
    except Exception:
        logger.warning("Precalentamiento de gol.gg fallo (no es grave)", exc_info=True)


def _header_index(table: BeautifulSoup) -> tuple[dict[str, int], list]:
    rows = table.find_all("tr")
    if not rows:
        raise GolGGError("gol.gg devolvio una tabla vacia.")
    headers = [cell.get_text(strip=True) for cell in rows[0].find_all(["th", "td"])]
    return {name: i for i, name in enumerate(headers)}, rows[1:]


def _cell(cells: list, index_map: dict[str, int], name: str) -> str:
    idx = index_map.get(name)
    if idx is None or idx >= len(cells):
        raise KeyError(name)
    return cells[idx].get_text(strip=True)


def _to_float(text: str) -> float:
    return float(text.replace("%", "").strip())


def _to_int(text: str) -> int:
    return int(float(text.replace("%", "").strip()))


def _duration_to_seconds(text: str) -> float:
    """gol.gg da la duracion de partida como 'MM:SS' (ej. '32:37'). Se
    convierte a segundos totales para poder ordenar/promediar numericamente."""
    minutes, seconds = text.strip().split(":")
    return int(minutes) * 60 + int(seconds)


def _seconds_to_duration(total_seconds: float) -> str:
    total = round(total_seconds)
    minutes, seconds = divmod(total, 60)
    return f"{minutes}:{seconds:02d}"


def _check_dropped_rows(kind: str, url: str, parsed: int, dropped: int, index_map: dict[str, int]) -> None:
    """Las filas que no se pueden parsear se descartan, pero ya no en
    silencio: si se descartan TODAS es casi seguro que gol.gg cambio las
    cabeceras de la tabla (no que "no haya datos"), asi que se avisa con un
    error claro; si solo son algunas, queda un warning en los logs."""
    if not dropped:
        return
    if parsed == 0:
        logger.error("gol.gg: se descartaron las %d filas de %s en %s. Cabeceras: %s", dropped, kind, url, list(index_map))
        raise GolGGError(
            f"gol.gg parece haber cambiado el formato de la tabla de {kind}, asi que no se pueden leer los datos."
        )
    logger.warning("gol.gg: se descartaron %d filas de %s (y %d si se leyeron) en %s", dropped, kind, parsed, url)


def fetch_team_stats(tournament: str | None = None) -> list[TeamStat]:
    url = _tournament_path("teams", tournament)
    table = _fetch_table(url, "playerslist")
    index_map, rows = _header_index(table)

    teams: list[TeamStat] = []
    dropped = 0
    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue
        try:
            teams.append(
                TeamStat(
                    name=_cell(cells, index_map, "Name"),
                    games=_to_int(_cell(cells, index_map, "Games")),
                    win_rate=_to_float(_cell(cells, index_map, "Win rate")),
                    kda=_to_float(_cell(cells, index_map, "K:D")),
                    gpm=_to_float(_cell(cells, index_map, "GPM")),
                    fb_pct=_to_float(_cell(cells, index_map, "FB%")),
                    towers_killed=_to_float(_cell(cells, index_map, "Towers killed")),
                    dragons_per_game=_to_float(_cell(cells, index_map, "DRAPG")),
                    avg_game_duration_seconds=_duration_to_seconds(_cell(cells, index_map, "Game duration")),
                )
            )
        except (KeyError, ValueError):
            dropped += 1
    _check_dropped_rows("equipos", url, len(teams), dropped, index_map)
    return teams


def fetch_player_stats(tournament: str | None = None) -> list[PlayerStat]:
    url = _tournament_path("players", tournament)
    table = _fetch_table(url, "playerslist")
    index_map, rows = _header_index(table)

    players: list[PlayerStat] = []
    dropped = 0
    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue
        try:
            players.append(
                PlayerStat(
                    name=_cell(cells, index_map, "Player"),
                    games=_to_int(_cell(cells, index_map, "Games")),
                    win_rate=_to_float(_cell(cells, index_map, "Win rate")),
                    kda=_to_float(_cell(cells, index_map, "KDA")),
                    csm=_to_float(_cell(cells, index_map, "CSM")),
                    avg_kills=_to_float(_cell(cells, index_map, "Avg kills")),
                    penta_kills=_to_int(_cell(cells, index_map, "Penta Kills")),
                    solo_kills=_to_int(_cell(cells, index_map, "Solo Kills")),
                )
            )
        except (KeyError, ValueError):
            dropped += 1
    _check_dropped_rows("jugadores", url, len(players), dropped, index_map)
    return players


def _weighted_avg(entries: list, attr: str) -> float:
    total_games = sum(e.games for e in entries)
    return round(sum(getattr(e, attr) * e.games for e in entries) / total_games, 2)


def aggregate_team_stats(tournaments: list[str]) -> list[TeamStat]:
    """Combina stats de equipos de varios torneos (ej. Spring+Summer) por nombre.

    Aproximacion razonable para "stats curiosas": promedio ponderado por
    partidos jugados en cada torneo. No es matematicamente exacto para ratios
    como K:D (combinar dos ratios promediando no es lo mismo que recalcular
    desde los totales de kills/deaths crudos), pero alcanza para este uso.
    """
    warm_stats_pages(team_tournaments=tournaments)
    by_name: dict[str, list[TeamStat]] = {}
    for tournament in tournaments:
        for team in fetch_team_stats(tournament):
            by_name.setdefault(team.name, []).append(team)

    merged: list[TeamStat] = []
    for name, entries in by_name.items():
        total_games = sum(e.games for e in entries)
        if total_games == 0:
            continue
        merged.append(
            TeamStat(
                name=name,
                games=total_games,
                win_rate=_weighted_avg(entries, "win_rate"),
                kda=_weighted_avg(entries, "kda"),
                gpm=_weighted_avg(entries, "gpm"),
                fb_pct=_weighted_avg(entries, "fb_pct"),
                towers_killed=_weighted_avg(entries, "towers_killed"),
                dragons_per_game=_weighted_avg(entries, "dragons_per_game"),
                avg_game_duration_seconds=_weighted_avg(entries, "avg_game_duration_seconds"),
            )
        )
    return merged


def aggregate_player_stats(tournaments: list[str]) -> list[PlayerStat]:
    by_name: dict[str, list[PlayerStat]] = {}
    warm_stats_pages(player_tournaments=tournaments)
    for tournament in tournaments:
        for player in fetch_player_stats(tournament):
            by_name.setdefault(player.name, []).append(player)

    merged: list[PlayerStat] = []
    for name, entries in by_name.items():
        total_games = sum(e.games for e in entries)
        if total_games == 0:
            continue
        merged.append(
            PlayerStat(
                name=name,
                games=total_games,
                win_rate=_weighted_avg(entries, "win_rate"),
                kda=_weighted_avg(entries, "kda"),
                csm=_weighted_avg(entries, "csm"),
                avg_kills=_weighted_avg(entries, "avg_kills"),
                penta_kills=sum(e.penta_kills for e in entries),
                solo_kills=sum(e.solo_kills for e in entries),
            )
        )
    return merged
