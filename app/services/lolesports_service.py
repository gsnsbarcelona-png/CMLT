import time as time_module
import unicodedata
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

LOLESPORTS_API_BASE = "https://esports-api.lolesports.com/persisted/gw"

# Ids resueltos a mano contra GET /persisted/gw/getLeagues (2026-08-30,
# emea_masters verificado el 2026-09-04). Estables desde hace años, pero
# podrian cambiar si Riot reestructura ligas.
LEAGUE_IDS = {
    "les": "105266074488398661",
    "lec": "98767991302996019",
    "emea_masters": "100695891328981122",
}
LEAGUE_LABELS = {
    "les": "LES",
    "lec": "LEC",
    "emea_masters": "EMEA Masters",
}
# Version sin espacios de LEAGUE_LABELS, para el hashtag de cierre (un
# hashtag con espacio no es un hashtag) -- "EMEAMasters" es como lo usa la
# propia cuenta oficial en sus tweets.
LEAGUE_HASHTAGS = {
    "les": "LES",
    "lec": "LEC",
    "emea_masters": "EMEAMasters",
}
LEAGUE_ORDER = ["les", "lec", "emea_masters"]

MADRID_TZ = ZoneInfo("Europe/Madrid")
WEEKDAY_ABBR = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]

UPCOMING_STATES = {"unstarted", "inProgress"}


class LoLEsportsError(Exception):
    pass


class TeamRosterNotFoundError(LoLEsportsError):
    """El nombre de equipo pedido no matchea ningun equipo de LES en getTeams."""


def normalize_team_name(name: str) -> str:
    """Saca acentos y pasa a minuscula -- lolesports.com y gol.gg no siempre
    usan el mismo nombre de equipo (ej. "UCAM Esports" vs "UCAM Esports Club",
    "Barca eSports" vs "Barça Esports" con tilde), asi que el matching entre
    ambas fuentes se hace por substring sobre el nombre normalizado."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


# getTeams devuelve ~1500 equipos de todas las ligas de Riot -- no cambia de
# un minuto a otro, asi que se cachea por mas tiempo que el calendario.
_TEAMS_CACHE_TTL_SECONDS = 3600
_teams_cache: tuple[float, list[dict]] | None = None


def _fetch_all_teams() -> list[dict]:
    global _teams_cache
    now = time_module.monotonic()
    if _teams_cache is not None and now - _teams_cache[0] < _TEAMS_CACHE_TTL_SECONDS:
        return _teams_cache[1]

    try:
        response = httpx.get(
            f"{LOLESPORTS_API_BASE}/getTeams",
            params={"hl": "en-US"},
            headers={"x-api-key": settings.lolesports_api_key},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LoLEsportsError(
            "No se pudo obtener el listado de equipos de LoL Esports. Intenta de nuevo en unos minutos."
        ) from exc

    try:
        teams = response.json()["data"]["teams"]
    except (KeyError, ValueError) as exc:
        raise LoLEsportsError("LoL Esports devolvio una respuesta inesperada.") from exc

    _teams_cache = (now, teams)
    return teams


@dataclass
class RosterPlayer:
    name: str
    role: str


def _find_les_team(team_name: str) -> dict:
    wanted = normalize_team_name(team_name)
    for team in _fetch_all_teams():
        if (team.get("homeLeague") or {}).get("name") != "LES":
            continue
        candidates = {normalize_team_name(team.get("name") or ""), normalize_team_name(team.get("code") or "")}
        if any(c and (wanted in c or c in wanted) for c in candidates):
            return team

    raise TeamRosterNotFoundError(f"No encontramos el equipo '{team_name}' en la LES.")


def fetch_les_team_roster_with_roles(team_name: str) -> list[RosterPlayer]:
    """Plantilla actual de un equipo de LES con el rol de cada jugador
    (top/jungle/mid/bottom/support), segun getTeams. TeamRosterNotFoundError
    si el nombre no matchea ningun equipo de la liga."""
    team = _find_les_team(team_name)
    return [
        RosterPlayer(name=p["summonerName"], role=p.get("role") or "")
        for p in team.get("players") or []
        if p.get("summonerName")
    ]


def fetch_les_team_roster(team_name: str) -> list[str]:
    """Nombres de invocador (summonerName) de la plantilla actual de un
    equipo de LES, segun getTeams. TeamRosterNotFoundError si el nombre no
    matchea ningun equipo de la liga."""
    return [p.name for p in fetch_les_team_roster_with_roles(team_name)]


def get_les_team_logo_url(team_name: str) -> str | None:
    """URL del escudo del equipo (campo "image" de getTeams, confirmado en
    vivo que lolesports.com ya lo trae para todos los equipos de LES -- no
    hace falta curar imagenes a mano). Best-effort: devuelve None en vez de
    levantar si el equipo no matchea o la API falla, porque esto es solo una
    sugerencia de imagen, no debe romper la generacion/publicacion del tweet."""
    try:
        team = _find_les_team(team_name)
    except LoLEsportsError:
        return None
    return team.get("image") or None


@dataclass
class MatchInfo:
    start_time: datetime  # aware, ya convertido a Europe/Madrid
    state: str
    league_slug: str
    block_name: str
    team1_name: str
    team1_code: str
    team2_name: str
    team2_code: str


def _parse_team(team: dict | None) -> tuple[str, str]:
    if not team:
        return "TBD", "TBD"
    return team.get("name") or "TBD", team.get("code") or "TBD"


# El calendario cambia poco (un partido que termina, uno que empieza), y los
# modos H2H/Duelo/Calendario lo piden varias veces seguidas: cache corta.
_EVENTS_CACHE_TTL_SECONDS = 90
_events_cache: dict[str, tuple[float, list[dict]]] = {}


def _fetch_league_events(league_slug: str) -> list[dict]:
    cached = _events_cache.get(league_slug)
    now = time_module.monotonic()
    if cached is not None and now - cached[0] < _EVENTS_CACHE_TTL_SECONDS:
        return cached[1]
    events = _fetch_league_events_uncached(league_slug)
    _events_cache[league_slug] = (now, events)
    return events


def _fetch_league_events_uncached(league_slug: str) -> list[dict]:
    league_id = LEAGUE_IDS[league_slug]
    try:
        response = httpx.get(
            f"{LOLESPORTS_API_BASE}/getSchedule",
            params={"hl": "es-ES", "leagueId": league_id},
            headers={"x-api-key": settings.lolesports_api_key},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LoLEsportsError(
            "No se pudo obtener el calendario de LoL Esports. Intenta de nuevo en unos minutos."
        ) from exc

    try:
        return response.json()["data"]["schedule"]["events"]
    except (KeyError, ValueError) as exc:
        raise LoLEsportsError("LoL Esports devolvio una respuesta inesperada.") from exc


def fetch_upcoming_matches(league_slugs: list[str], now: datetime | None = None) -> list[MatchInfo]:
    if now is None:
        now = datetime.now(timezone.utc)
    # "Proximos 7 dias" se define por dias de calendario (hora Madrid), no por
    # una ventana rigida de 168 horas: un partido tarde el septimo dia debe
    # entrar igual, aunque "ahora" sea temprano a la mañana de hoy.
    horizon_date = now.astimezone(MADRID_TZ).date() + timedelta(days=7)
    horizon = datetime.combine(horizon_date, time(23, 59, 59), tzinfo=MADRID_TZ)

    matches: list[MatchInfo] = []
    for slug in league_slugs:
        for event in _fetch_league_events(slug):
            if event.get("type") != "match":
                continue
            state = event.get("state")
            if state not in UPCOMING_STATES:
                continue

            start_time = datetime.fromisoformat(event["startTime"].replace("Z", "+00:00"))
            if state == "unstarted" and start_time > horizon:
                continue

            teams = event.get("match", {}).get("teams") or [None, None]
            team1_name, team1_code = _parse_team(teams[0] if len(teams) > 0 else None)
            team2_name, team2_code = _parse_team(teams[1] if len(teams) > 1 else None)

            matches.append(
                MatchInfo(
                    start_time=start_time.astimezone(MADRID_TZ),
                    state=state,
                    league_slug=slug,
                    block_name=event.get("blockName") or "",
                    team1_name=team1_name,
                    team1_code=team1_code,
                    team2_name=team2_name,
                    team2_code=team2_code,
                )
            )

    matches.sort(key=lambda m: m.start_time)
    _relabel_final_four_blocks(matches)
    return matches


def _relabel_final_four_blocks(matches: list[MatchInfo]) -> None:
    # La API devuelve blockName "Final" para TODOS los cruces de la Final Four,
    # pero el formato real (confirmado en lesesports.es) es "Rey de la Colina":
    # 3ro vs 4to, el ganador vs el 2do, y recien el ganador de ese cruce llega a
    # la gran final contra el 1ro. Solo el ultimo partido cronologico de cada
    # liga es la final real; los anteriores son cruces previos, no finales.
    by_league: dict[str, list[MatchInfo]] = {}
    for match in matches:
        if match.block_name == "Final":
            by_league.setdefault(match.league_slug, []).append(match)

    for league_matches in by_league.values():
        if len(league_matches) < 2:
            continue
        ordered = sorted(league_matches, key=lambda m: m.start_time)
        for i, match in enumerate(ordered[:-1], start=1):
            match.block_name = f"Final Four - Cruce {i}"
        ordered[-1].block_name = "GRAN FINAL"


def fetch_todays_matches(league_slugs: list[str] | None = None, now: datetime | None = None) -> list[MatchInfo]:
    """Partidos programados para HOY (fecha de calendario, hora Madrid)."""
    if league_slugs is None:
        league_slugs = ["les"]
    if now is None:
        now = datetime.now(timezone.utc)
    today = now.astimezone(MADRID_TZ).date()

    return [m for m in fetch_upcoming_matches(league_slugs, now=now) if m.start_time.date() == today]


def fetch_matches_today_or_tomorrow(
    league_slugs: list[str] | None = None, now: datetime | None = None
) -> list[MatchInfo]:
    """Partidos programados para HOY o MAÑANA (fecha de calendario, hora
    Madrid) -- usado por el Duelo 1v1, que quiere previsualizar tambien el
    partido de mañana si hoy no hay ninguno."""
    if league_slugs is None:
        league_slugs = ["les"]
    if now is None:
        now = datetime.now(timezone.utc)
    today = now.astimezone(MADRID_TZ).date()
    tomorrow = today + timedelta(days=1)

    return [
        m for m in fetch_upcoming_matches(league_slugs, now=now) if m.start_time.date() in (today, tomorrow)
    ]


LEAGUE_HANDLE_SETTINGS = {
    "les": lambda: settings.league_handle_les,
    "lec": lambda: settings.league_handle_lec,
    "emea_masters": lambda: settings.league_handle_emea_masters,
}


def league_label(league_slugs: list[str]) -> str:
    ordered_slugs = [s for s in LEAGUE_ORDER if s in league_slugs]
    return " + ".join(LEAGUE_LABELS[s] for s in ordered_slugs)


def closing_tags(league_slugs: list[str]) -> str:
    """Arrobas de liga + hashtags de liga + hashtags personalizados, para
    agregar al final de un tweet de calendario (plano o hype por igual)."""
    ordered_slugs = [s for s in LEAGUE_ORDER if s in league_slugs]
    handles = [LEAGUE_HANDLE_SETTINGS[s]() for s in ordered_slugs]
    hashtags = [f"#{LEAGUE_HASHTAGS[s]}" for s in ordered_slugs]
    return " ".join(handles + hashtags + settings.custom_hashtag_list)


def _display_code(code: str) -> str:
    # TBD siempre significa "a definir por el partido anterior" en fases de
    # eliminacion directa (unico caso en el que la API devuelve TBD) -> mostrar
    # "Ganador" es mas claro para el lector que el codigo crudo de la API.
    return "Ganador" if code == "TBD" else code


def _match_line(match: MatchInfo) -> str:
    prefix = "🔴 EN VIVO " if match.state == "inProgress" else ""
    if match.block_name == "GRAN FINAL":
        prefix += "🏆 "
    day = WEEKDAY_ABBR[match.start_time.weekday()]
    block_suffix = f" ({match.block_name})" if match.block_name else ""
    return (
        f"{prefix}{day} {match.start_time:%d/%m %H:%M} "
        f"{_display_code(match.team1_code)} 🆚 {_display_code(match.team2_code)}{block_suffix}"
    )




def format_schedule_tweet(matches: list[MatchInfo], league_slugs: list[str]) -> str:
    label = league_label(league_slugs)

    if not matches:
        return f"No hay partidos programados de {label} en los proximos 7 dias."

    start_dates = [m.start_time.date() for m in matches]
    date_range = f"{min(start_dates):%d/%m} al {max(start_dates):%d/%m}"

    lines = [f"📅 Calendario {label} ({date_range})", ""]
    lines.extend(_match_line(m) for m in matches)
    return "\n".join(lines)
