"""Top / ranking (top N de una categoría, no solo el líder)."""
from dataclasses import dataclass
from typing import Callable

from app.services.golgg.models import GolGGError, PlayerStat, TeamStat, TopRankingCandidate, TopRankingEntry
from app.services.golgg.stats import _seconds_to_duration


def _fmt_ratio(value: float) -> str:
    return f"{round(value, 2):g}"


def _fmt_pct(value: float) -> str:
    return f"{round(value, 1):g}%"


@dataclass
class TopRankingCategorySpec:
    label: str
    level: str  # "player" | "team"
    attr: str  # atributo de PlayerStat/TeamStat a ordenar
    ascending: bool  # True = menor valor es mejor (solo la de duración)
    unit_label: str  # texto que acompaña la cifra en el tweet
    emoji: str
    value_formatter: Callable[[float], str]


TOP_RANKING_CATEGORIES: dict[str, TopRankingCategorySpec] = {
    "player_kda": TopRankingCategorySpec(
        label="KDA", level="player", attr="kda", ascending=False,
        unit_label="de KDA", emoji="🔥", value_formatter=_fmt_ratio,
    ),
    "player_csm": TopRankingCategorySpec(
        label="Farmeo (CS por minuto)", level="player", attr="csm", ascending=False,
        unit_label="de CSM", emoji="🌾", value_formatter=_fmt_ratio,
    ),
    "team_dragons": TopRankingCategorySpec(
        label="Dragones por partida", level="team", attr="dragons_per_game", ascending=False,
        unit_label="dragones/partida", emoji="🐉", value_formatter=_fmt_ratio,
    ),
    "team_towers": TopRankingCategorySpec(
        label="Torres por partida", level="team", attr="towers_killed", ascending=False,
        unit_label="torres/partida", emoji="🏰", value_formatter=_fmt_ratio,
    ),
    "team_fb": TopRankingCategorySpec(
        label="Primeras sangres (%)", level="team", attr="fb_pct", ascending=False,
        unit_label="de primera sangre", emoji="🩸", value_formatter=_fmt_pct,
    ),
    "team_fastest": TopRankingCategorySpec(
        label="Equipos que más rápido cierran sus partidas", level="team",
        attr="avg_game_duration_seconds", ascending=True,
        unit_label="de duración media", emoji="⏱️", value_formatter=_seconds_to_duration,
    ),
}

TOP_RANKING_CATEGORY_LABELS: dict[str, str] = {key: spec.label for key, spec in TOP_RANKING_CATEGORIES.items()}

TOP_RANKING_TOP_N = 3


def compute_top_ranking_candidate(
    category: str, team_stats: list[TeamStat], player_stats: list[PlayerStat], top_n: int = TOP_RANKING_TOP_N
) -> TopRankingCandidate:
    spec = TOP_RANKING_CATEGORIES.get(category)
    if spec is None:
        raise GolGGError(f"Categoría de top no reconocida: {category}.")

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
        emoji=spec.emoji,
    )
