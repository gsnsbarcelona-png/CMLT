"""Excepciones y dataclasses compartidas del paquete gol.gg."""
from dataclasses import dataclass


class GolGGError(Exception):
    pass


class StatFocusNotFoundError(GolGGError):
    """El foco pedido por el usuario (equipo/jugador) no matchea ningún candidato."""


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
    emoji: str
    title: str
    question: str
    hook: str = ""  # primera linea con dato + sujeto; vacio = se usa el titulo generico


@dataclass
class ActiveConfig:
    season: str
    tournament: str
    year_tournaments: list[str]
    lec_tournament: str
    emea_masters_tournaments: list[str]


@dataclass
class MatchResult:
    winner: str
    loser: str
    winner_maps: int
    loser_maps: int
    date: str  # "YYYY-MM-DD", ya viene así de gol.gg (ordenable como string)
    tournament: str


@dataclass
class RecentForm:
    wins: int
    losses: int
    games: int


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


@dataclass
class LeagueComparisonCandidate:
    kind: str
    subject: str  # equipo/jugador de LES protagonista
    fact_sentence: str  # las dos cifras (LES y LEC) lado a lado
    nuance: str  # matiz obligatorio sobre nivel/muestra distintos
    hook: str = ""  # primera linea con dato + sujeto; vacio = cabecera generica


@dataclass
class TopRankingEntry:
    name: str
    team: str | None  # gol.gg no da el equipo de cada jugador -- siempre None en categorías de jugador, nunca inventado
    value: float  # crudo, para ordenar/testear
    value_display: str  # ya formateado según la categoría (ej. "9.4", "62.5%", "29:10")
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
    emoji: str
