from app.services.golgg_service import PlayerStat, StatCandidate
from app.services.lolesports_service import RosterPlayer

ROLE_LABELS = {
    "top": "TOP",
    "jungle": "JUNGLA",
    "mid": "MID",
    "bottom": "ADC",
    "support": "SUPPORT",
}


def reconcile_player_casing(names: list[str], known_players: list[str]) -> list[str]:
    """Los nombres de invocador de lolesports.com vienen en MAYUSCULAS (ej.
    "ANDARIEL"); gol.gg tiene la capitalizacion real del nick (ej. "Andariel").
    Si hay match exacto case-insensitive se usa esa, si no se deja el nombre
    tal cual vino (mejor mostrar algo que nada)."""
    by_lower = {p.lower(): p for p in known_players}
    return [by_lower.get(name.lower(), name) for name in names]


def _group_by_role(roster: list[RosterPlayer]) -> dict[str, list[RosterPlayer]]:
    groups: dict[str, list[RosterPlayer]] = {}
    for player in roster:
        if not player.role:
            continue
        groups.setdefault(player.role, []).append(player)
    return groups


def _pick_starter(
    players: list[RosterPlayer], stats_by_name: dict[str, PlayerStat]
) -> tuple[RosterPlayer, PlayerStat] | None:
    """Si un rol tiene mas de un jugador en la plantilla (suplentes), se
    queda con el que mas partidos jugo esta temporada en gol.gg -- proxy
    razonable de titular, no hay alineaciones oficiales confirmadas de
    antemano en la API. Ignora jugadores sin datos en gol.gg (no se puede
    armar el duelo con alguien sin stats)."""
    candidates = [(p, stats_by_name[p.name.lower()]) for p in players if p.name.lower() in stats_by_name]
    if not candidates:
        return None
    return max(candidates, key=lambda pair: pair[1].games)


def _fmt(value: float) -> str:
    return f"{round(value, 2):g}"


def _duel_hook(role_label: str, name_a: str, stat_a: PlayerStat, name_b: str, stat_b: PlayerStat) -> str:
    """Los dos KDA y quien lleva ventaja por cuanto (solo cifras reales)."""
    head = f"{role_label}: {name_a} ({_fmt(stat_a.kda)} de KDA) vs {name_b} ({_fmt(stat_b.kda)})"
    diff = round(stat_a.kda - stat_b.kda, 2)
    if diff == 0:
        return f"{head}, igualados"
    leader, trailer = (name_a, name_b) if diff > 0 else (name_b, name_a)
    return f"{head}: {leader} le saca {_fmt(abs(diff))} a {trailer}"


def _duel_fact(name_a: str, stat_a: PlayerStat, name_b: str, stat_b: PlayerStat) -> str:
    return f"{name_a} suma {stat_a.games} partidos esta temporada; {name_b}, {stat_b.games}."


def compute_duel_candidates(
    roster_a: list[RosterPlayer], roster_b: list[RosterPlayer], player_stats: list[PlayerStat]
) -> list[StatCandidate]:
    """Un StatCandidate por rol donde ambos equipos tienen un titular con
    datos de KDA en gol.gg -- si un rol no tiene match en el otro equipo, o
    ninguno de los dos tiene stats, ese rol se omite (no se inventa el
    duelo)."""
    stats_by_name = {p.name.lower(): p for p in player_stats}
    groups_a = _group_by_role(roster_a)
    groups_b = _group_by_role(roster_b)

    candidates: list[StatCandidate] = []
    for role in sorted(set(groups_a) & set(groups_b)):
        picked_a = _pick_starter(groups_a[role], stats_by_name)
        picked_b = _pick_starter(groups_b[role], stats_by_name)
        if picked_a is None or picked_b is None:
            continue
        player_a, stat_a = picked_a
        player_b, stat_b = picked_b
        role_label = ROLE_LABELS.get(role, role.upper())

        candidates.append(
            StatCandidate(
                kind="individual_duel",
                subject=f"{player_a.name} vs {player_b.name}",
                fact_sentence=_duel_fact(player_a.name, stat_a, player_b.name, stat_b),
                emoji="🔥",
                title=f"DUELO DE {role_label}",
                question="¿Quién se lleva ese carril?",
                hook=_duel_hook(role_label, player_a.name, stat_a, player_b.name, stat_b),
            )
        )
    return candidates
