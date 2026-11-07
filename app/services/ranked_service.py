import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from app.services.golgg_service import StatCandidate

LOLPROS_BASE = "https://lolpros.gg"
# Igual que gol.gg, un User-Agent de navegador evita bloqueos por defecto.
LOLPROS_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


logger = logging.getLogger(__name__)


class RankedError(Exception):
    pass


# Solo consulta en vivo al generar (sin historial persistido, decision del
# usuario) -- pero una cache corta evita repetir ~30 pedidos a lolpros.gg si
# se genera "ranked" varias veces seguidas en pocos minutos.
_CACHE_TTL_SECONDS = 900
_http_cache: dict[str, tuple[float, str]] = {}
# Cache negativa corta: un slug inexistente (404/500) no se reintenta durante
# unos minutos. Guarda (instante, status).
_NEGATIVE_TTL_SECONDS = 600
_negative_cache: dict[str, tuple[float, int]] = {}
_CACHE_MAX_ENTRIES = 200
_NOT_FOUND_STATUSES = {404, 500}  # lolpros.gg devuelve 500 para algunos slugs inexistentes (visto en vivo)
_RATE_LIMIT_STATUSES = {403, 429}


def _purge(cache: dict, ttl: float, now: float) -> None:
    """Purga simple: primero lo vencido y, si sigue lleno, lo más viejo."""
    if len(cache) < _CACHE_MAX_ENTRIES:
        return
    for key in [k for k, v in cache.items() if now - v[0] >= ttl]:
        del cache[key]
    while len(cache) >= _CACHE_MAX_ENTRIES:
        del cache[min(cache, key=lambda k: cache[k][0])]


def _cached_get(url: str) -> tuple[int, str]:
    """Devuelve (status_code, texto). 404/500 -> "no encontrado" (status
    distinto de 200, cacheado poco tiempo). 403/429 -> RankedError (nos estan
    limitando; no se cachea ni se reintenta). Otros >=400 -> "no encontrado"
    sin cachear."""
    now = time.monotonic()
    cached = _http_cache.get(url)
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return 200, cached[1]
    negative = _negative_cache.get(url)
    if negative is not None and now - negative[0] < _NEGATIVE_TTL_SECONDS:
        return negative[1], ""

    try:
        response = httpx.get(url, headers=LOLPROS_HEADERS, timeout=10.0)
    except httpx.HTTPError as exc:
        raise RankedError(
            "No se pudo consultar lolpros.gg. Intenta de nuevo en unos minutos."
        ) from exc

    status = response.status_code
    if status in _RATE_LIMIT_STATUSES:
        logger.warning("lolpros.gg respondió %s para %s (limitación de peticiones)", status, url)
        raise RankedError(
            "lolpros.gg nos está limitando las peticiones. Espera unos minutos y vuelve a intentarlo."
        )
    if status >= 400:
        if status in _NOT_FOUND_STATUSES:
            _purge(_negative_cache, _NEGATIVE_TTL_SECONDS, now)
            _negative_cache[url] = (now, status)
        else:
            logger.warning("lolpros.gg respondió %s para %s", status, url)
        return status, ""

    _purge(_http_cache, _CACHE_TTL_SECONDS, now)
    _http_cache[url] = (now, response.text)
    return 200, response.text


@dataclass
class PlayerRank:
    player: str
    slug: str
    tier: str
    lp: int
    wins: int
    losses: int
    date: str
    peak_tier: str | None = None
    peak_lp: int | None = None
    peak_wins: int | None = None
    peak_losses: int | None = None
    peak_date: str | None = None

    @property
    def winrate(self) -> float:
        total = self.wins + self.losses
        return round(100 * self.wins / total, 1) if total else 0.0


# El slug de lolpros.gg no siempre es el nombre de gol.gg en minuscula
# (confirmado en vivo, 7 casos reales de la LES): a veces el nick real usa
# una grafia distinta a la de gol.gg (ej. "Macaquinho" en gol.gg es en
# realidad "Macaquiño"/slug "macaquino", nada que ver con sacar un acento),
# o le sobra/falta un numero/guion. Verificados a mano cruzando LP, equipo y
# companeros de equipo antes de cargarlos aca -- no se adivinan a ciegas.
KNOWN_SLUG_OVERRIDES = {
    "macaquinho": "macaquino",  # Barca eSports (BAR) -- gol.gg dice "Macaquinho", el jugador es "Macaquiño"
    "kaii1": "kaii",
    "mercy9": "mercy",  # Team Heretics Academy (HRTS)
    "pasamelcelo": "pasameelcelo",  # UB Alma Mater -- confirmado por su propia página de equipo
    "adrianlanei": "adrianlaneitor",  # UB Alma Mater -- LP cruzado con la lista de compañeros de Pasameelcelo
    "nightslayer": "night-slayer",
    "koido": "koldo",  # Barca eSports -- confirmado por el usuario, página propia con tab "BARÇA ESPORTS"
}


def _slugify(name: str) -> str:
    normalized = name.strip().lower()
    return KNOWN_SLUG_OVERRIDES.get(normalized, normalized)


def _parse_rank_block(soup: BeautifulSoup, section_id: str) -> dict | None:
    """DOM confirmado en vivo: div#current-elo / div#peak-elo, cada uno con
    .card.rank-display -> p.rank (tier), p.league-points ("2698 LP"),
    p.games > span.wins / span.losses, time[title] ("DD/MM")."""
    section = soup.find(id=section_id)
    if section is None:
        return None
    card = section.find(class_="rank-display")
    if card is None:
        return None
    try:
        tier = card.find(class_="rank").get_text(strip=True)
        lp_text = card.find(class_="league-points").get_text(strip=True)
        lp = int(lp_text.replace("LP", "").strip())
        wins = int(card.find(class_="wins").get_text(strip=True))
        losses = int(card.find(class_="losses").get_text(strip=True))
        date = card.find("time").get_text(strip=True)
    except (AttributeError, ValueError):
        return None
    return {"tier": tier, "lp": lp, "wins": wins, "losses": losses, "date": date}


def fetch_player_rank(player_name: str) -> PlayerRank | None:
    """None = no se encontro/no hay datos de ranked para este jugador (no es
    un error -- puede pasar, se omite del tweet en vez de romperlo)."""
    slug = _slugify(player_name)
    status, html = _cached_get(f"{LOLPROS_BASE}/player/{slug}")
    if status != 200:
        return None

    soup = BeautifulSoup(html, "html.parser")
    current = _parse_rank_block(soup, "current-elo")
    if current is None:
        return None
    peak = _parse_rank_block(soup, "peak-elo")

    return PlayerRank(
        player=player_name,
        slug=slug,
        tier=current["tier"],
        lp=current["lp"],
        wins=current["wins"],
        losses=current["losses"],
        date=current["date"],
        peak_tier=peak["tier"] if peak else None,
        peak_lp=peak["lp"] if peak else None,
        peak_wins=peak["wins"] if peak else None,
        peak_losses=peak["losses"] if peak else None,
        peak_date=peak["date"] if peak else None,
    )


def _safe_fetch_player_rank(player_name: str) -> PlayerRank | None:
    """Igual que fetch_player_rank, pero nunca propaga RankedError -- un
    problema de red puntual en UN jugador (dentro de una tanda de ~30 en
    paralelo) no debe tirar abajo toda la generacion."""
    try:
        return fetch_player_rank(player_name)
    except RankedError as exc:
        logger.warning("Rango de %s no resuelto: %s", player_name, exc)
        return None


def fetch_all_player_ranks(
    player_names: list[str], max_workers: int = 12
) -> tuple[list[PlayerRank], list[str]]:
    """Resuelve el rango de varios jugadores en paralelo (si no, ~30 pedidos
    secuenciales a lolpros.gg tardarian demasiado). Devuelve (resueltos,
    nombres_no_resueltos) -- jugadores sin match o con un fallo de red
    puntual no rompen el tweet, solo se excluyen."""
    names = sorted({n.strip() for n in player_names if n.strip()})
    if not names:
        return [], []

    resolved: list[PlayerRank] = []
    unresolved: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(_safe_fetch_player_rank, names)
        for name, rank in zip(names, results):
            if rank is None:
                unresolved.append(name)
            else:
                resolved.append(rank)
    return resolved, unresolved


TIER_ORDER = [
    "Iron",
    "Bronze",
    "Silver",
    "Gold",
    "Platinum",
    "Emerald",
    "Diamond",
    "Master",
    "Grandmaster",
    "Challenger",
]
# Lookup case-insensitive: juntar "Grand" + "Master" da "GrandMaster" (M
# mayuscula), pero TIER_ORDER tiene "Grandmaster" -- comparar en minuscula
# evita ese desajuste de casing.
_TIER_ORDER_LOOKUP = {name.lower(): i for i, name in enumerate(TIER_ORDER)}


def _tier_rank(tier: str) -> tuple[int, int]:
    """(indice de tier, division invertida) para comparar tiers entre si con
    max()/sort. Dos cosas que lolpros.gg no deja parsear con un split()[0]
    ingenuo: el nombre del tier no es consistente (a veces "Grandmaster"
    junto, a veces "Grand Master" separado -- confirmado en vivo, causaba
    que cualquiera en Grand Master quedara por debajo de Iron) y los tiers
    con division (Iron a Diamond) traen el numero de division al final
    (ej. "Diamond 2", division mas baja es mejor)."""
    if not tier:
        return (-1, 0)
    parts = tier.split()
    division = 0
    if parts and parts[-1].isdigit():
        division = int(parts[-1])
        parts = parts[:-1]
    tier_name = "".join(parts)
    tier_index = _TIER_ORDER_LOOKUP.get(tier_name.lower(), -1)
    # Master+ no tiene division (0 no resta nada); para el resto, division
    # mas baja es mejor -> se invierte para que ordene bien de menor a mayor.
    division_score = (5 - division) if division else 0
    return (tier_index, division_score)


def compute_rank_candidates(ranks: list[PlayerRank]) -> list[StatCandidate]:
    candidates: list[StatCandidate] = []

    for rank in ranks:
        candidates.append(
            StatCandidate(
                kind="player_rank_current",
                subject=rank.player,
                fact_sentence=(
                    f"{rank.player} está en {rank.tier} con {rank.lp} LP "
                    f"({rank.wins}-{rank.losses}, {rank.winrate}%) en SoloQ ahora mismo."
                ),
                emoji="🏆",
                title="RANGO EN SOLOQ",
                question="¿En qué elo estás tú?",
            )
        )

    if ranks:
        leader = max(ranks, key=lambda r: (_tier_rank(r.tier), r.lp))
        candidates.append(
            StatCandidate(
                kind="player_rank_leader",
                subject=leader.player,
                fact_sentence=(
                    f"{leader.player} es el jugador con el rango más alto de la LES ahora mismo: "
                    f"{leader.tier} ({leader.lp} LP)."
                ),
                emoji="👑",
                title="EL ELO MÁS ALTO DE LA LIGA",
                question="¿Quién le hace sombra?",
            )
        )

    for rank in ranks:
        if rank.peak_tier is None or rank.peak_lp is None:
            continue
        tier_diff = _tier_rank(rank.peak_tier)[0] - _tier_rank(rank.tier)[0]
        lp_diff = rank.peak_lp - rank.lp if tier_diff == 0 else None
        if tier_diff > 0 or (lp_diff is not None and lp_diff >= 100):
            candidates.append(
                StatCandidate(
                    kind="player_rank_peak_drop",
                    subject=rank.player,
                    fact_sentence=(
                        f"{rank.player} llegó a tocar {rank.peak_tier} ({rank.peak_lp} LP) en SoloQ, "
                        f"hoy está en {rank.tier} ({rank.lp} LP)."
                    ),
                    emoji="📉",
                    title="LEJOS DE SU PICO",
                    question="¿Vuelve a ese nivel antes de que termine el split?",
                )
            )

    return candidates


def _rank_key(rank: PlayerRank) -> tuple[tuple[int, int], int]:
    return (_tier_rank(rank.tier), rank.lp)


def _rank_gap_sentence(rank_a: PlayerRank, rank_b: PlayerRank) -> str:
    """Quien va arriba y por cuanto. Solo hay diferencia numerica real (LP)
    si ambos estan en el mismo tier+division; si no, se dice quien va por
    delante sin inventar una cifra."""
    key_a, key_b = _rank_key(rank_a), _rank_key(rank_b)
    if key_a == key_b:
        return "Están igualados en SoloQ."
    higher, lower = (rank_a, rank_b) if key_a > key_b else (rank_b, rank_a)
    if _tier_rank(higher.tier) == _tier_rank(lower.tier):
        gap = higher.lp - lower.lp
        return f"Va arriba {higher.player}, por {gap} LP."
    return f"Va arriba {higher.player}: {higher.tier} contra {lower.tier}."


def compute_player_vs_player_candidate(rank_a: PlayerRank, rank_b: PlayerRank) -> StatCandidate:
    """Compara el elo actual de dos jugadores puntuales, uno contra el otro."""
    return StatCandidate(
        kind="player_rank_vs_player",
        subject=f"{rank_a.player} vs {rank_b.player}",
        fact_sentence=_rank_gap_sentence(rank_a, rank_b),
        emoji="⚔️",
        title="DUELO DE ELO",
        question="¿A cuál te gustaría tener en tu equipo?",
        hook=(
            f"{rank_a.player} ({rank_a.tier}, {rank_a.lp} LP) vs "
            f"{rank_b.player} ({rank_b.tier}, {rank_b.lp} LP) en SoloQ"
        ),
    )


def compute_team_vs_team_candidate(
    team_a: str, team_b: str, ranks_a: list[PlayerRank], ranks_b: list[PlayerRank]
) -> StatCandidate:
    """Compara el jugador con mejor elo de cada plantilla -- no un promedio:
    los tiers no tienen una escala numerica real (Iron a Challenger no es
    lineal), asi que "el mas alto de cada equipo" es el dato defendible."""
    if not ranks_a:
        raise RankedError(f"No se pudo obtener el elo de ningún jugador de {team_a}.")
    if not ranks_b:
        raise RankedError(f"No se pudo obtener el elo de ningún jugador de {team_b}.")

    best_a = max(ranks_a, key=lambda r: (_tier_rank(r.tier), r.lp))
    best_b = max(ranks_b, key=lambda r: (_tier_rank(r.tier), r.lp))

    return StatCandidate(
        kind="team_rank_vs_team",
        subject=f"{team_a} vs {team_b}",
        fact_sentence=_rank_gap_sentence(best_a, best_b),
        emoji="🛡️",
        title="MEJOR ELO DE CADA PLANTILLA",
        question="¿A cuál prefieres tener en tu equipo?",
        hook=(
            f"Mejor elo de {team_a}: {best_a.player} ({best_a.tier}, {best_a.lp} LP). "
            f"De {team_b}: {best_b.player} ({best_b.tier}, {best_b.lp} LP)"
        ),
    )
