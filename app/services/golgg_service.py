import random
import time
from dataclasses import dataclass
from typing import Callable

import httpx
from bs4 import BeautifulSoup

from app.config import settings

GOLGG_BASE = "https://gol.gg"
# gol.gg devuelve 403 con el User-Agent default de httpx -> hace falta uno de navegador.
GOLGG_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class GolGGError(Exception):
    pass


class StatFocusNotFoundError(GolGGError):
    """El foco pedido por el usuario (equipo/jugador) no matchea ningun candidato."""


# gol.gg no cambia segundo a segundo, y una sola generacion de Stats con
# "equipos" ya pega varias veces a las mismas paginas (compute_head_to_head_candidates
# recorre los mismos torneos que aggregate_team_stats, y el usuario suele
# generar varias veces seguidas mientras prueba/edita). Una cache corta en
# memoria evita repetir esos pedidos sin arriesgar datos muy desactualizados.
_CACHE_TTL_SECONDS = 300
_http_cache: dict[str, tuple[float, str]] = {}


def _cached_get(url: str) -> str:
    cached = _http_cache.get(url)
    now = time.monotonic()
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = httpx.get(url, headers=GOLGG_HEADERS, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GolGGError(
            "No se pudo obtener las estadisticas de gol.gg. Intenta de nuevo en unos minutos."
        ) from exc

    _http_cache[url] = (now, response.text)
    return response.text


def discover_tournaments(season: str | None = None, region: str | None = "ES") -> list[dict]:
    """Lista los torneos disponibles en gol.gg para una temporada (por defecto
    la configurada) y region (por defecto ES). Pega directo al endpoint AJAX
    que usa la propia pagina https://gol.gg/tournament/list/ (descubierto
    inspeccionando su JS) -- pensado como herramienta de mantenimiento para
    encontrar el nombre exacto de un torneo nuevo en cada split, sin tener
    que buscarlo a mano. No pasa por la cache de _cached_get (es un POST,
    y es una consulta ocasional de mantenimiento, no parte del flujo normal
    de generacion)."""
    season = season or settings.golgg_season
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


@dataclass
class TeamStat:
    name: str
    games: int
    win_rate: float
    kda: float
    gpm: float
    fb_pct: float
    towers_killed: float
    dragons_per_game: float
    avg_game_duration_seconds: float


@dataclass
class PlayerStat:
    name: str
    games: int
    win_rate: float
    kda: float
    csm: float
    avg_kills: float
    penta_kills: int
    solo_kills: int


@dataclass
class StatCandidate:
    kind: str
    subject: str
    fact_sentence: str
    plano_emoji: str
    plano_title: str
    plano_question: str


def get_year_tournaments() -> list[str]:
    return [t.strip() for t in settings.golgg_year_tournaments.split(",") if t.strip()]


def get_lec_tournament() -> str:
    return settings.lec_tournament


def get_emea_masters_tournaments() -> list[str]:
    return [t.strip() for t in settings.emea_masters_tournaments.split(",") if t.strip()]


def _tournament_path(prefix: str, tournament: str | None = None) -> str:
    tournament = tournament or settings.golgg_tournament
    # "ALL" funciona para el segmento split en todos los torneos probados
    # (regular season Y playoffs), a diferencia de inferir el split del nombre
    # del torneo -- confirmado en vivo: para "LES 2026 Summer Playoffs" el
    # listado de equipos necesita split-Playoffs pero el de jugadores
    # split-Summer/ALL (gol.gg es inconsistente entre sus propias paginas).
    # "ALL" evita tener que adivinar cual de los dos hace falta en cada caso.
    return (
        f"{GOLGG_BASE}/{prefix}/list/season-{settings.golgg_season}/"
        f"split-ALL/tournament-{tournament}/"
    )


def _fetch_table(url: str, table_class: str) -> BeautifulSoup:
    html = _cached_get(url)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=table_class)
    if table is None:
        raise GolGGError("gol.gg devolvio una pagina sin la tabla de estadisticas esperada.")
    return table


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


def fetch_team_stats(tournament: str | None = None) -> list[TeamStat]:
    table = _fetch_table(_tournament_path("teams", tournament), "playerslist")
    index_map, rows = _header_index(table)

    teams: list[TeamStat] = []
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
            continue
    return teams


def fetch_player_stats(tournament: str | None = None) -> list[PlayerStat]:
    table = _fetch_table(_tournament_path("players", tournament), "playerslist")
    index_map, rows = _header_index(table)

    players: list[PlayerStat] = []
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
            continue
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


@dataclass
class MatchResult:
    winner: str
    loser: str
    winner_maps: int
    loser_maps: int
    date: str  # "YYYY-MM-DD", ya viene asi de gol.gg (ordenable como string)
    tournament: str


def fetch_match_results(tournament: str) -> list[MatchResult]:
    url = f"{GOLGG_BASE}/tournament/tournament-matchlist/{tournament}/"
    table = _fetch_table(url, "table_list")
    rows = table.find_all("tr")[1:]

    # Esta tabla tiene headers vacios para las columnas de equipos (a diferencia
    # de teams/list y players/list), asi que no se puede parsear por nombre de
    # columna -- los equipos siempre estan en las celdas 1 y 3 (indices fijos,
    # verificados contra el HTML real), PERO cual de los dos gano NO es fijo por
    # posicion: gol.gg marca al ganador con la clase css "text_victory" en la
    # celda que le corresponda (a veces la 1, a veces la 3). Ignorar esto y
    # asumir que la celda 1 siempre es el ganador invierte el resultado en esos
    # casos -- confirmado con un partido real (UCAM le gano a Barca en la
    # celda 3, marcado "text_victory" ahi y no en la celda 1). El score de la
    # celda 2 siempre viene en el orden "celda1 - celda3" (no "ganador-perdedor"),
    # asi que hay que reordenarlo segun quien gano para sacar mapas ganados/perdidos.
    results: list[MatchResult] = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        team_1, team_2 = cells[1], cells[3]
        name_1, name_2 = team_1.get_text(strip=True), team_2.get_text(strip=True)
        score_text = cells[2].get_text(strip=True)
        date_text = cells[6].get_text(strip=True) if len(cells) > 6 else ""
        if not name_1 or not name_2:
            continue

        score_parts = [p.strip() for p in score_text.split("-")]
        if len(score_parts) != 2:
            continue
        try:
            maps_1, maps_2 = int(score_parts[0]), int(score_parts[1])
        except ValueError:
            continue

        if "text_victory" in (team_1.get("class") or []):
            winner, loser = name_1, name_2
            winner_maps, loser_maps = maps_1, maps_2
        elif "text_victory" in (team_2.get("class") or []):
            winner, loser = name_2, name_1
            winner_maps, loser_maps = maps_2, maps_1
        else:
            # No se pudo determinar el ganador por clase css -> se descarta la
            # fila en vez de arriesgarse a invertir el resultado.
            continue

        results.append(
            MatchResult(
                winner=winner,
                loser=loser,
                winner_maps=winner_maps,
                loser_maps=loser_maps,
                date=date_text,
                tournament=tournament,
            )
        )
    return results


def fetch_all_match_results(tournaments: list[str]) -> list[MatchResult]:
    all_results: list[MatchResult] = []
    for tournament in tournaments:
        all_results.extend(fetch_match_results(tournament))
    return all_results


def find_head_to_head(team_a: str, team_b: str, tournaments: list[str]) -> StatCandidate | None:
    """Busca el candidato de rivalidad de un par puntual de equipos elegido por el usuario."""
    wanted = {team_a.strip().lower(), team_b.strip().lower()}
    for candidate in compute_head_to_head_candidates(tournaments):
        parts = {p.strip().lower() for p in candidate.subject.split(" vs ")}
        if parts == wanted:
            return candidate
    return None


def compute_head_to_head_candidates(tournaments: list[str]) -> list[StatCandidate]:
    all_results = fetch_all_match_results(tournaments)

    pair_wins: dict[frozenset, dict[str, int]] = {}
    pair_maps: dict[frozenset, dict[str, int]] = {}
    for result in all_results:
        pair = frozenset({result.winner, result.loser})
        if len(pair) != 2:
            continue
        record = pair_wins.setdefault(pair, {})
        record[result.winner] = record.get(result.winner, 0) + 1

        maps_record = pair_maps.setdefault(pair, {})
        maps_record[result.winner] = maps_record.get(result.winner, 0) + result.winner_maps
        maps_record[result.loser] = maps_record.get(result.loser, 0) + result.loser_maps

    candidates: list[StatCandidate] = []
    for pair, record in pair_wins.items():
        team_a, team_b = sorted(pair)
        wins_a = record.get(team_a, 0)
        wins_b = record.get(team_b, 0)
        total = wins_a + wins_b
        if total == 0:
            continue

        maps_record = pair_maps.get(pair, {})
        maps_a = maps_record.get(team_a, 0)
        maps_b = maps_record.get(team_b, 0)

        if wins_a == wins_b:
            fact = (
                f"{team_a} y {team_b} se repartieron sus {total} cruces de la temporada: "
                f"{wins_a}-{wins_b} (mapas: {maps_a}-{maps_b})."
            )
        else:
            leader, leader_wins, leader_maps, other, other_wins, other_maps = (
                (team_a, wins_a, maps_a, team_b, wins_b, maps_b)
                if wins_a > wins_b
                else (team_b, wins_b, maps_b, team_a, wins_a, maps_a)
            )
            fact = (
                f"{leader} le gano a {other} en {leader_wins} de sus {total} cruces esta temporada "
                f"({leader_wins}-{other_wins}, mapas: {leader_maps}-{other_maps})."
            )

        candidates.append(
            StatCandidate(
                kind="team_head_to_head",
                subject=f"{team_a} vs {team_b}",
                fact_sentence=fact,
                plano_emoji="🤜🤛",
                plano_title="RIVALIDAD DEL AÑO",
                plano_question="¿Se repite la historia la proxima vez que se crucen?",
            )
        )
    return candidates


@dataclass
class RecentForm:
    wins: int
    losses: int
    games: int


def _recent_form(team: str, all_results: list[MatchResult], n: int = 5) -> RecentForm | None:
    team_results = [r for r in all_results if team in (r.winner, r.loser)]
    if not team_results:
        return None
    team_results.sort(key=lambda r: r.date, reverse=True)
    recent = team_results[:n]
    wins = sum(1 for r in recent if r.winner == team)
    return RecentForm(wins=wins, losses=len(recent) - wins, games=len(recent))


@dataclass
class HeadToHeadPreviewData:
    team_a: str
    team_b: str
    total_wins_a: int
    total_wins_b: int
    total_maps_a: int
    total_maps_b: int
    last_meeting: MatchResult | None
    last_win_by_a: MatchResult | None
    last_win_by_b: MatchResult | None
    recent_form_a: RecentForm | None
    recent_form_b: RecentForm | None


def build_head_to_head_preview(team_a: str, team_b: str, tournaments: list[str]) -> HeadToHeadPreviewData:
    all_results = fetch_all_match_results(tournaments)
    pair_results = [r for r in all_results if {r.winner, r.loser} == {team_a, team_b}]

    wins_by_a = [r for r in pair_results if r.winner == team_a]
    wins_by_b = [r for r in pair_results if r.winner == team_b]

    return HeadToHeadPreviewData(
        team_a=team_a,
        team_b=team_b,
        total_wins_a=len(wins_by_a),
        total_wins_b=len(wins_by_b),
        total_maps_a=sum(r.winner_maps if r.winner == team_a else r.loser_maps for r in pair_results),
        total_maps_b=sum(r.winner_maps if r.winner == team_b else r.loser_maps for r in pair_results),
        last_meeting=max(pair_results, key=lambda r: r.date) if pair_results else None,
        last_win_by_a=max(wins_by_a, key=lambda r: r.date) if wins_by_a else None,
        last_win_by_b=max(wins_by_b, key=lambda r: r.date) if wins_by_b else None,
        recent_form_a=_recent_form(team_a, all_results),
        recent_form_b=_recent_form(team_b, all_results),
    )


def format_h2h_context(preview: HeadToHeadPreviewData, today_context: str | None = None) -> str:
    """Bloque de hechos en texto plano para pasarle a la IA. Cuando un dato no
    esta disponible lo dice explicitamente (nunca lo omite en silencio), para
    que la IA nunca tenga que adivinar/inventar para rellenar el hueco."""
    lines = [f"Partido: {preview.team_a} vs {preview.team_b}"]
    if today_context:
        lines.append(today_context)

    total = preview.total_wins_a + preview.total_wins_b
    if total:
        lines.append(
            f"Historial directo esta temporada: {preview.team_a} {preview.total_wins_a}-"
            f"{preview.total_wins_b} {preview.team_b} (mapas: {preview.total_maps_a}-{preview.total_maps_b})."
        )
    else:
        lines.append("Historial directo: sin enfrentamientos previos registrados esta temporada.")

    if preview.last_meeting:
        m = preview.last_meeting
        lines.append(f"Ultimo enfrentamiento ({m.date}, {m.tournament}): gano {m.winner} a {m.loser}.")
    else:
        lines.append("Ultimo enfrentamiento: no hay registro.")

    if preview.last_win_by_a and preview.last_win_by_a is not preview.last_meeting:
        lines.append(f"Ultima vez que gano {preview.team_a}: {preview.last_win_by_a.date}.")
    if preview.last_win_by_b and preview.last_win_by_b is not preview.last_meeting:
        lines.append(f"Ultima vez que gano {preview.team_b}: {preview.last_win_by_b.date}.")

    for team, form in ((preview.team_a, preview.recent_form_a), (preview.team_b, preview.recent_form_b)):
        if form:
            lines.append(f"Forma reciente de {team} (ultimos {form.games} partidos): {form.wins}V-{form.losses}D.")
        else:
            lines.append(f"Forma reciente de {team}: sin datos disponibles.")

    return "\n".join(lines)


def format_h2h_variant_plain(preview: HeadToHeadPreviewData, angle: str, today_context: str | None = None) -> str:
    """Version sin IA de la preview head-to-head. Misma idea de las 4 partes
    (gancho / dato protagonista / matiz / pregunta) con frases fijas por
    angulo, usando solo los datos reales que haya -- si algo falta, frase
    neutra en vez de inventar."""
    total = preview.total_wins_a + preview.total_wins_b
    lines = [f"🥊 {preview.team_a} 🆚 {preview.team_b}"]
    if today_context:
        lines.append(today_context)

    if angle == "historial":
        if total:
            headline = (
                f"Historial de la temporada: {preview.team_a} {preview.total_wins_a}-"
                f"{preview.total_wins_b} {preview.team_b} (mapas: {preview.total_maps_a}-{preview.total_maps_b})."
            )
        else:
            headline = f"Primer cruce del año entre {preview.team_a} y {preview.team_b} esta temporada."

        if preview.last_meeting:
            nuance = f"El ultimo cruce ({preview.last_meeting.date}) lo gano {preview.last_meeting.winner}."
        else:
            nuance = "Todavia no hay antecedentes directos esta temporada."

        question = "¿Se repite la historia hoy?"
    else:
        parts = []
        for team, form in ((preview.team_a, preview.recent_form_a), (preview.team_b, preview.recent_form_b)):
            parts.append(f"{team} {form.wins}V-{form.losses}D" if form else f"{team} sin datos recientes")
        headline = f"Forma reciente: {' / '.join(parts)}."

        if total:
            leader = preview.team_a if preview.total_wins_a >= preview.total_wins_b else preview.team_b
            nuance = f"En el historial de la temporada manda {leader} ({preview.total_wins_a}-{preview.total_wins_b})."
        else:
            nuance = "Sin cruces previos esta temporada para comparar."

        question = "¿Quien llega mejor hoy?"

    lines.extend([headline, nuance, f"{question} 👀"])
    return "\n".join(lines)


def compute_candidates(
    team_stats: list[TeamStat], player_stats: list[PlayerStat], categories: set[str]
) -> list[StatCandidate]:
    candidates: list[StatCandidate] = []

    if "teams" in categories and team_stats:
        best_kda = max(team_stats, key=lambda t: t.kda)
        candidates.append(
            StatCandidate(
                kind="team_kda",
                subject=best_kda.name,
                fact_sentence=f"{best_kda.name} tiene el mejor ratio K:D de la liga: {best_kda.kda} ({best_kda.games} partidos jugados).",
                plano_emoji="⚔️",
                plano_title="RATIO DE MUERTES DEL SPLIT",
                plano_question="¿Alguien lo va a superar antes de que termine el split?",
            )
        )

        best_winrate = max(team_stats, key=lambda t: t.win_rate)
        wins = round(best_winrate.games * best_winrate.win_rate / 100)
        candidates.append(
            StatCandidate(
                kind="team_winrate",
                subject=best_winrate.name,
                fact_sentence=f"{best_winrate.name} lidera el winrate de la liga con {best_winrate.win_rate}% ({wins}-{best_winrate.games - wins}).",
                plano_emoji="📈",
                plano_title="EL MEJOR REGISTRO DE LA LIGA",
                plano_question="¿Quien le puede parar el paso?",
            )
        )

        best_fb = max(team_stats, key=lambda t: t.fb_pct)
        candidates.append(
            StatCandidate(
                kind="team_fb",
                subject=best_fb.name,
                fact_sentence=f"{best_fb.name} se lleva la primera sangre en el {best_fb.fb_pct}% de sus partidos, el mejor registro de la liga.",
                plano_emoji="🩸",
                plano_title="SIEMPRE PRIMEROS EN SANGRAR",
                plano_question="¿Es la clave de su temporada?",
            )
        )

        if len(team_stats) >= 2:
            worst_winrate = min(team_stats, key=lambda t: t.win_rate)
            if worst_winrate.name != best_winrate.name:
                candidates.append(
                    StatCandidate(
                        kind="team_winrate_contrast",
                        subject=f"{best_winrate.name} vs {worst_winrate.name}",
                        fact_sentence=(
                            f"{best_winrate.name} lidera la liga con {best_winrate.win_rate}% de victorias, "
                            f"mientras {worst_winrate.name} tiene el peor registro con {worst_winrate.win_rate}%."
                        ),
                        plano_emoji="⚖️",
                        plano_title="LAS DOS CARAS DE LA LIGA",
                        plano_question="¿Se cruzan antes de que termine el split?",
                    )
                )

    if "players" in categories and player_stats:
        best_kda = max(player_stats, key=lambda p: p.kda)
        candidates.append(
            StatCandidate(
                kind="player_kda",
                subject=best_kda.name,
                fact_sentence=f"{best_kda.name} cerro el split con {best_kda.kda} de KDA en {best_kda.games} partidos.",
                plano_emoji="🔥",
                plano_title="KDA DEL SPLIT",
                plano_question="¿Puede sostener ese nivel bajo presion?",
            )
        )

        best_csm = max(player_stats, key=lambda p: p.csm)
        candidates.append(
            StatCandidate(
                kind="player_csm",
                subject=best_csm.name,
                fact_sentence=f"{best_csm.name} promedia {best_csm.csm} de CSM, el mejor farmeo de la liga.",
                plano_emoji="🌾",
                plano_title="LA MEJOR FARMEADA DE LA LIGA",
                plano_question="¿Eso alcanza para ganarle a las junglas rivales?",
            )
        )

        best_solo = max(player_stats, key=lambda p: p.solo_kills)
        if best_solo.solo_kills > 0:
            candidates.append(
                StatCandidate(
                    kind="player_solo_kills",
                    subject=best_solo.name,
                    fact_sentence=f"{best_solo.name} acumula {best_solo.solo_kills} solo kills este split, el maximo de la liga.",
                    plano_emoji="🗡️",
                    plano_title="EL QUE MAS 1V1 GANA",
                    plano_question="¿Te animas a duelear contra el?",
                )
            )

        best_penta = max(player_stats, key=lambda p: p.penta_kills)
        if best_penta.penta_kills > 0:
            candidates.append(
                StatCandidate(
                    kind="player_penta_kills",
                    subject=best_penta.name,
                    fact_sentence=f"{best_penta.name} suma {best_penta.penta_kills} pentakill(s) este split.",
                    plano_emoji="💥",
                    plano_title="PENTAKILL",
                    plano_question="¿Viste el clip?",
                )
            )

    return candidates


def pick_candidate(candidates: list[StatCandidate], focus: str | None = None) -> StatCandidate:
    pool = candidates
    if focus:
        focus_lower = focus.strip().lower()
        pool = [c for c in candidates if focus_lower in c.subject.lower()]
        if not pool:
            raise StatFocusNotFoundError(f"No encontramos datos de '{focus}' en {settings.golgg_tournament}.")
    if not pool:
        raise GolGGError(f"No hay datos estadisticos disponibles para {settings.golgg_tournament} todavia.")
    return random.choice(pool)


TEAM_LEVEL_KINDS = {
    "team_kda",
    "team_winrate",
    "team_fb",
    "team_winrate_contrast",
    "team_head_to_head",
    "team_rank_vs_team",
    "individual_duel",  # el candidato real tiene subject "JugadorA vs JugadorB";
    # las arrobas de equipo salen de un StatCandidate sintetico con subject
    # "EquipoA vs EquipoB" armado aparte solo para el cierre (igual que H2H).
    "top_team_towers",
    "top_team_dragons",
    "top_team_fb",
    "top_team_fastest",
    # top_player_kda y top_player_csm NO estan aca a proposito: son
    # categorias de jugador, no arroban equipo (gol.gg no expone el equipo
    # de cada jugador en la tabla de stats, no se inventa).
}


def get_team_handles() -> dict[str, str]:
    """Parsea settings.team_handles ("Nombre:@handle,Nombre:@handle,...").

    Cargado a mano por el usuario -- no se adivinan handles de equipo."""
    handles: dict[str, str] = {}
    for entry in settings.team_handles.split(","):
        if ":" not in entry:
            continue
        name, handle = entry.split(":", 1)
        name, handle = name.strip(), handle.strip()
        if name and handle:
            handles[name] = handle
    return handles


def stat_closing_tags(candidate: StatCandidate) -> str:
    """Arrobas de equipo (solo si el candidato es de nivel equipo) + arroba de
    liga + hashtags personalizados, para agregar al final de un tweet de stats
    (plano o IA por igual)."""
    team_handles: list[str] = []
    if candidate.kind in TEAM_LEVEL_KINDS:
        handles_map = get_team_handles()
        team_names = [n.strip() for n in candidate.subject.split(" vs ")]
        team_handles = [handles_map[name] for name in team_names if name in handles_map]

    parts = team_handles + [settings.league_handle_les] + settings.custom_hashtag_list
    return " ".join(parts)


def format_stat_tweet_plain(candidate: StatCandidate) -> str:
    return (
        f"{candidate.plano_emoji} {candidate.plano_title}\n"
        f"{candidate.fact_sentence}\n"
        f"{candidate.plano_question} {candidate.plano_emoji}"
    )


@dataclass
class LeagueComparisonCandidate:
    kind: str
    subject: str  # equipo/jugador de LES protagonista
    fact_sentence: str  # las dos cifras (LES y LEC) lado a lado
    nuance: str  # matiz obligatorio sobre nivel/muestra distintos


def _average(entries: list, attr: str) -> float:
    return round(sum(getattr(e, attr) for e in entries) / len(entries), 2)


LEVEL_NUANCE = "Ojo: son ligas de nivel y muestra distintos, no equivale 1 a 1."


def compute_league_comparison_candidates(
    les_teams: list[TeamStat],
    les_players: list[PlayerStat],
    lec_teams: list[TeamStat],
    lec_players: list[PlayerStat],
) -> list[LeagueComparisonCandidate]:
    """Candidatos LES-vs-LEC: mejor de LES en una metrica contra el promedio
    de LEC en esa misma metrica. Se limita a metricas donde esta comparacion
    (mejor-de-LES vs promedio-de-LEC) no suene despectiva hacia la LES -- se
    evitan a proposito metricas de ritmo/economia (GPM, CSM) donde la LEC
    suele ser estructuralmente mas alta y la comparacion quedaria injusta."""
    candidates: list[LeagueComparisonCandidate] = []

    if les_teams and lec_teams:
        best_kda = max(les_teams, key=lambda t: t.kda)
        lec_avg_kda = _average(lec_teams, "kda")
        candidates.append(
            LeagueComparisonCandidate(
                kind="team_kda",
                subject=best_kda.name,
                fact_sentence=(
                    f"{best_kda.name} tiene un ratio K:D de {best_kda.kda} en la LES, frente al "
                    f"{lec_avg_kda} de promedio entre los equipos de la LEC."
                ),
                nuance=LEVEL_NUANCE,
            )
        )

        best_winrate = max(les_teams, key=lambda t: t.win_rate)
        lec_avg_winrate = _average(lec_teams, "win_rate")
        candidates.append(
            LeagueComparisonCandidate(
                kind="team_winrate",
                subject=best_winrate.name,
                fact_sentence=(
                    f"{best_winrate.name} lidera la LES con {best_winrate.win_rate}% de victorias, "
                    f"frente al {lec_avg_winrate}% de promedio en la LEC."
                ),
                nuance=LEVEL_NUANCE,
            )
        )

        best_fb = max(les_teams, key=lambda t: t.fb_pct)
        lec_avg_fb = _average(lec_teams, "fb_pct")
        candidates.append(
            LeagueComparisonCandidate(
                kind="team_fb",
                subject=best_fb.name,
                fact_sentence=(
                    f"{best_fb.name} se lleva la primera sangre en el {best_fb.fb_pct}% de sus "
                    f"partidos en la LES, frente al {lec_avg_fb}% de promedio en la LEC."
                ),
                nuance=LEVEL_NUANCE,
            )
        )

    if les_players and lec_players:
        best_kda = max(les_players, key=lambda p: p.kda)
        lec_avg_kda = _average(lec_players, "kda")
        candidates.append(
            LeagueComparisonCandidate(
                kind="player_kda",
                subject=best_kda.name,
                fact_sentence=(
                    f"{best_kda.name} cerro con {best_kda.kda} de KDA en la LES, frente al "
                    f"{lec_avg_kda} de promedio entre los jugadores de la LEC."
                ),
                nuance="El KDA en la LES suele estar inflado vs la LEC por la diferencia de nivel.",
            )
        )

    return candidates


def pick_league_comparison_candidate(
    candidates: list[LeagueComparisonCandidate], focus: str | None = None
) -> LeagueComparisonCandidate:
    pool = candidates
    if focus:
        focus_lower = focus.strip().lower()
        pool = [c for c in candidates if focus_lower in c.subject.lower()]
        if not pool:
            raise StatFocusNotFoundError(f"No encontramos datos de '{focus}' para comparar con la LEC.")
    if not pool:
        raise GolGGError("No hay datos suficientes de LES y LEC todavia para comparar.")
    return random.choice(pool)


def format_league_comparison_plain(candidate: LeagueComparisonCandidate, tone: str) -> str:
    if tone == "debate":
        header = "🤔 DEBATE LES-LEC"
        question = "¿Se sostendria esa cifra en la LEC? 👀"
    else:
        header = "🔎 DATO LES-LEC"
        question = "¿Aguantaria el ritmo LEC? 👀"

    lines = [header, candidate.fact_sentence, candidate.nuance, question]
    return "\n".join(lines)


def format_league_comparison_context(candidate: LeagueComparisonCandidate, tone: str) -> str:
    return f"Tono pedido: {tone}\nProtagonista: {candidate.subject}\nDato real: {candidate.fact_sentence}\nMatiz obligatorio: {candidate.nuance}"


# ---------------------------------------------------------------------------
# Top / ranking (top N de una categoria, no solo el lider)
# ---------------------------------------------------------------------------


def _fmt_ratio(value: float) -> str:
    return f"{round(value, 2):g}"


def _fmt_pct(value: float) -> str:
    return f"{round(value, 1):g}%"


@dataclass
class TopRankingCategorySpec:
    label: str
    level: str  # "player" | "team"
    attr: str  # atributo de PlayerStat/TeamStat a ordenar
    ascending: bool  # True = menor valor es mejor (solo la de duracion)
    unit_label: str  # texto que acompaña la cifra en el tweet
    plano_emoji: str
    value_formatter: Callable[[float], str]


TOP_RANKING_CATEGORIES: dict[str, TopRankingCategorySpec] = {
    "player_kda": TopRankingCategorySpec(
        label="KDA", level="player", attr="kda", ascending=False,
        unit_label="de KDA", plano_emoji="🔥", value_formatter=_fmt_ratio,
    ),
    "player_csm": TopRankingCategorySpec(
        label="Farmeo (CS por minuto)", level="player", attr="csm", ascending=False,
        unit_label="de CSM", plano_emoji="🌾", value_formatter=_fmt_ratio,
    ),
    "team_dragons": TopRankingCategorySpec(
        label="Dragones por partida", level="team", attr="dragons_per_game", ascending=False,
        unit_label="dragones/partida", plano_emoji="🐉", value_formatter=_fmt_ratio,
    ),
    "team_towers": TopRankingCategorySpec(
        label="Torres por partida", level="team", attr="towers_killed", ascending=False,
        unit_label="torres/partida", plano_emoji="🏰", value_formatter=_fmt_ratio,
    ),
    "team_fb": TopRankingCategorySpec(
        label="Primeras sangres (%)", level="team", attr="fb_pct", ascending=False,
        unit_label="de primera sangre", plano_emoji="🩸", value_formatter=_fmt_pct,
    ),
    "team_fastest": TopRankingCategorySpec(
        label="Equipos que mas rapido cierran sus partidas", level="team",
        attr="avg_game_duration_seconds", ascending=True,
        unit_label="de duracion media", plano_emoji="⏱️", value_formatter=_seconds_to_duration,
    ),
}

TOP_RANKING_CATEGORY_LABELS: dict[str, str] = {key: spec.label for key, spec in TOP_RANKING_CATEGORIES.items()}

TOP_RANKING_TOP_N = 3


@dataclass
class TopRankingEntry:
    name: str
    team: str | None  # gol.gg no da el equipo de cada jugador -- siempre None en categorias de jugador, nunca inventado
    value: float  # crudo, para ordenar/testear
    value_display: str  # ya formateado segun la categoria (ej. "9.4", "62.5%", "29:10")
    games: int


@dataclass
class TopRankingCandidate:
    kind: str  # "top_player_kda", "top_team_towers", ...
    category_label: str
    level: str  # "player" | "team"
    entries: list[TopRankingEntry]  # 1 a TOP_RANKING_TOP_N, ya ordenadas (mejor primero)
    total_pool_size: int  # cuantos jugadores/equipos tenian datos en total esta consulta
    unit_label: str
    league_average_display: str | None
    plano_emoji: str


def compute_top_ranking_candidate(
    category: str, team_stats: list[TeamStat], player_stats: list[PlayerStat], top_n: int = TOP_RANKING_TOP_N
) -> TopRankingCandidate:
    spec = TOP_RANKING_CATEGORIES.get(category)
    if spec is None:
        raise GolGGError(f"Categoria de top no reconocida: {category}.")

    pool = player_stats if spec.level == "player" else team_stats
    if not pool:
        raise GolGGError(f"No hay datos de gol.gg para calcular el top de {spec.label}.")

    # ascending=True (menos es mejor, solo "duracion media") -> orden normal;
    # ascending=False (mas es mejor, el resto) -> orden invertido. Nunca se usa
    # max()/solo-el-lider como en compute_candidates: aca siempre hace falta
    # la lista completa ordenada para poder armar el top 3.
    ranked = sorted(pool, key=lambda e: getattr(e, spec.attr), reverse=not spec.ascending)

    entries = [
        TopRankingEntry(
            name=e.name,
            team=None,
            value=round(getattr(e, spec.attr), 2),
            value_display=spec.value_formatter(getattr(e, spec.attr)),
            games=e.games,
        )
        for e in ranked[:top_n]
    ]

    league_average_display = None
    if pool:
        avg = sum(getattr(e, spec.attr) for e in pool) / len(pool)
        league_average_display = spec.value_formatter(avg)

    return TopRankingCandidate(
        kind=f"top_{category}",
        category_label=spec.label,
        level=spec.level,
        entries=entries,
        total_pool_size=len(pool),
        unit_label=spec.unit_label,
        league_average_display=league_average_display,
        plano_emoji=spec.plano_emoji,
    )


def format_top_ranking_context(candidate: TopRankingCandidate) -> str:
    """Bloque de hechos en texto plano para pasarle a la IA -- misma logica que
    el resto de la app: si algo no esta disponible (menos de un top 3 completo,
    sin dato de contraste) lo dice explicitamente, nunca lo omite en silencio."""
    lines = [f"Categoria: {candidate.category_label} ({settings.golgg_tournament})."]
    if candidate.total_pool_size < TOP_RANKING_TOP_N:
        lines.append(
            f"Aviso: solo hay {candidate.total_pool_size} con datos suficientes este split "
            "(no hay un top 3 completo, no inventes posiciones que faltan)."
        )
    for i, entry in enumerate(candidate.entries, start=1):
        lines.append(f"{i}. {entry.name} - {entry.value_display} {candidate.unit_label} ({entry.games} partidos).")
    if candidate.league_average_display:
        lines.append(f"Dato de contraste (media de la liga en esta categoria): {candidate.league_average_display} {candidate.unit_label}.")
    else:
        lines.append("Dato de contraste (media de la liga): no disponible.")
    return "\n".join(lines)


def format_top_ranking_plain(candidate: TopRankingCandidate, variant: str) -> str:
    header = f"{candidate.plano_emoji} TOP {candidate.category_label.upper()} — {settings.golgg_tournament}"
    lines = [header]

    if variant == "top1":
        leader = candidate.entries[0]
        lines.append(f"{leader.name} manda con {leader.value_display} {candidate.unit_label} ({leader.games} partidos).")
        if candidate.league_average_display:
            lines.append(f"Media de la liga: {candidate.league_average_display} {candidate.unit_label}.")
        lines.append(f"¿Se mantiene arriba? {candidate.plano_emoji}")
    else:
        if candidate.total_pool_size < TOP_RANKING_TOP_N:
            lines.append(f"Solo hay {candidate.total_pool_size} con datos suficientes este split:")
        for i, entry in enumerate(candidate.entries, start=1):
            lines.append(f"{i}. {entry.name} — {entry.value_display} {candidate.unit_label}")
        lines.append(f"¿Se mantiene el top 1? {candidate.plano_emoji}")

    return "\n".join(lines)
