import time as time_module
import unicodedata
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.services.phrasing import choose

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
WEEKDAY_ABBR = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

UPCOMING_STATES = {"unstarted", "inProgress"}


class LoLEsportsError(Exception):
    pass


class TeamRosterNotFoundError(LoLEsportsError):
    """El nombre de equipo pedido no matchea ningún equipo de LES en getTeams."""


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
        raise LoLEsportsError("LoL Esports devolvió una respuesta inesperada.") from exc

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
        raise LoLEsportsError("LoL Esports devolvió una respuesta inesperada.") from exc


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


@dataclass
class ResultInfo:
    start_time: datetime  # aware, hora Madrid
    league_slug: str
    block_name: str
    team1_name: str
    team1_code: str
    team2_name: str
    team2_code: str
    score1: int
    score2: int
    # Series ganadas seguidas por el ganador contando esta (0 = no calculado).
    # Sale de los eventos ya descargados: si la API solo trae una ventana del
    # split, es un minimo real (nunca inflado).
    winner_streak: int = 0

    @property
    def winner_code(self) -> str:
        return self.team1_code if self.score1 > self.score2 else self.team2_code


RESULTS_LOOKBACK_DAYS = 7


def fetch_latest_results(
    league_slugs: list[str], now: datetime | None = None, lookback_days: int = RESULTS_LOOKBACK_DAYS
) -> list[ResultInfo]:
    """Resultados de la ULTIMA jornada con partidos terminados (el dia de
    calendario, hora Madrid, mas reciente con al menos un partido completado
    en los ultimos `lookback_days`). Solo partidos con marcador real
    (gameWins de la API); nunca se inventa un resultado."""
    if now is None:
        now = datetime.now(timezone.utc)
    oldest = (now.astimezone(MADRID_TZ) - timedelta(days=lookback_days)).date()

    results: list[ResultInfo] = []
    history: list[tuple[str, datetime, str, str, int, int]] = []  # (liga, hora, cod1, cod2, s1, s2) de TODO lo terminado
    final_pool: list[ResultInfo] = []  # TODAS las "Final" de la liga (cualquier estado/fecha) para el relabel
    for slug in league_slugs:
        for event in _fetch_league_events(slug):
            if event.get("type") != "match":
                continue
            teams = event.get("match", {}).get("teams") or []
            if (event.get("blockName") or "") == "Final" and event.get("startTime"):
                # Aunque no este completada o quede fuera de la ventana, cuenta
                # para saber cual es la ultima Final cronologica de la liga.
                pool_start = datetime.fromisoformat(event["startTime"].replace("Z", "+00:00")).astimezone(MADRID_TZ)
                n1, c1 = _parse_team(teams[0] if len(teams) > 0 else None)
                n2, c2 = _parse_team(teams[1] if len(teams) > 1 else None)
                final_info = ResultInfo(pool_start, slug, "Final", n1, c1, n2, c2, 0, 0)
                final_pool.append(final_info)
            else:
                final_info = None
            if event.get("state") != "completed":
                continue
            if len(teams) < 2 or not teams[0] or not teams[1]:
                continue
            try:
                score1 = int(teams[0]["result"]["gameWins"])
                score2 = int(teams[1]["result"]["gameWins"])
            except (KeyError, TypeError, ValueError):
                continue
            if score1 == score2:
                continue
            start_time = datetime.fromisoformat(event["startTime"].replace("Z", "+00:00")).astimezone(MADRID_TZ)
            if start_time.astimezone(timezone.utc) > now:
                continue
            name1, code1 = _parse_team(teams[0])
            name2, code2 = _parse_team(teams[1])
            history.append((slug, start_time, code1, code2, score1, score2))
            info = final_info or ResultInfo(
                start_time, slug, event.get("blockName") or "", name1, code1, name2, code2, score1, score2
            )
            info.score1, info.score2 = score1, score2
            results.append(info)

    _relabel_final_four_blocks(final_pool)
    results = [r for r in results if r.start_time.date() >= oldest]

    if not results:
        return []
    latest_day = max(r.start_time.date() for r in results)
    day_results = [r for r in results if r.start_time.date() == latest_day]
    day_results.sort(key=lambda r: r.start_time)
    for r in day_results:
        r.winner_streak = _winner_streak(r, history)
    return day_results


def _winner_streak(result: ResultInfo, history: list[tuple[str, datetime, str, str, int, int]]) -> int:
    """Series consecutivas ganadas por el ganador de `result` hasta ese partido
    (incluido), segun los partidos terminados de la misma liga."""
    code = result.winner_code
    if not code or code == "TBD":
        return 0
    games = sorted(
        (h for h in history if h[0] == result.league_slug and h[1] <= result.start_time and code in (h[2], h[3])),
        key=lambda h: h[1],
        reverse=True,
    )
    streak = 0
    for _slug, _start, c1, c2, s1, s2 in games:
        won = (c1 == code) == (s1 > s2)
        if not won:
            break
        streak += 1
    return streak


STREAK_MIN = 3
TWEET_LIMIT = 280


def _results_header(results: list[ResultInfo], league_slugs: list[str], suffix: str = "") -> str:
    label = league_label(league_slugs)
    day = results[0].start_time
    return choose(
        [
            f"🏁 Resultados {label} ({day:%d/%m}){suffix}",
            f"📊 Así quedó la jornada de {label} ({day:%d/%m}){suffix}",
        ]
    )


def _result_line(r: ResultInfo) -> str:
    winner_first = r.score1 > r.score2
    w_code, l_code = (r.team1_code, r.team2_code) if winner_first else (r.team2_code, r.team1_code)
    w_score, l_score = max(r.score1, r.score2), min(r.score1, r.score2)
    block = f" ({r.block_name})" if r.block_name else ""
    mark = "🏆" if r.block_name == "GRAN FINAL" else "✅"
    streak = f" 🔥{r.winner_streak} seguidas" if r.winner_streak >= STREAK_MIN else ""
    return f"{mark} {_display_code(w_code)} {w_score}-{l_score} {_display_code(l_code)}{block}{streak}"


def format_results_tweet(results: list[ResultInfo], league_slugs: list[str], max_chars: int | None = None) -> str:
    """Tweet de resultados. Con `max_chars`, si no caben todos los partidos se
    recorta por el final con "…y X partidos más" (los datos mostrados siguen
    siendo reales; el hilo completo sale de format_results_thread)."""
    header = _results_header(results, league_slugs)
    lines = [_result_line(r) for r in results]
    text = "\n".join([header, "", *lines])
    if max_chars is None or len(text) <= max_chars:
        return text
    for keep in range(len(lines) - 1, 0, -1):
        missing = len(lines) - keep
        more = f"…y {missing} partido más" if missing == 1 else f"…y {missing} partidos más"
        text = "\n".join([header, "", *lines[:keep], more])
        if len(text) <= max_chars:
            return text
    return text


def format_results_thread(results: list[ResultInfo], league_slugs: list[str], closing: str = "") -> list[str]:
    """Todos los resultados repartidos en tweets de <=280 caracteres (cada
    uno con su "(n/total)"); el cierre de arrobas/hashtags va en el ultimo."""
    lines = [_result_line(r) for r in results]
    reserve = len(" (9/9)")
    chunks: list[list[str]] = [[]]
    for line in lines:
        trial = "\n".join([*chunks[-1], line])
        if chunks[-1] and len(trial) + reserve + 60 > TWEET_LIMIT:
            chunks.append([line])
        else:
            chunks[-1].append(line)
    total = len(chunks)
    tweets: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        header = _results_header(results, league_slugs, suffix=f" ({i}/{total})")
        body = "\n".join([header, "", *chunk])
        tweets.append(body)
    if closing:
        # El cierre va en el ultimo tweet; si no cabe, en un tweet aparte.
        if len(tweets[-1]) + 2 + len(closing) <= TWEET_LIMIT:
            tweets[-1] += f"\n\n{closing}"
        else:
            tweets.append(closing)
    return tweets


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
        return f"No hay partidos programados de {label} en los próximos 7 días."

    start_dates = [m.start_time.date() for m in matches]
    date_range = f"{min(start_dates):%d/%m} al {max(start_dates):%d/%m}"

    lines = [f"📅 Calendario {label} ({date_range})", ""]
    lines.extend(_match_line(m) for m in matches)
    return "\n".join(lines)
