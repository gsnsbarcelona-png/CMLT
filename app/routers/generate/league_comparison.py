from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.routers.generate._shared import _closing_tags_for, _generate_variants
from app.services.crossover_service import CrossoverDataError, compute_player_crossover_candidates
from app.services.golgg_service import (
    GolGGError,
    StatFocusNotFoundError,
    compute_league_comparison_candidates,
    fetch_player_stats,
    fetch_team_stats,
    format_league_comparison_plain,
    get_lec_tournament,
    warm_stats_pages,
    pick_league_comparison_candidate,
)

router = APIRouter()


def _with_lec_handle(closing: str) -> str:
    """El Cruce LEC compara LES con LEC: ademas de @LESESPORTS (que ya pone
    stat_closing_tags) se arroba a la LEC, justo despues de la arroba de LES.
    Coherente con closing_tags() de calendario: arrobas de liga en orden
    LES, LEC y sin hashtags de liga extra (el cierre de stats no los lleva)."""
    lec = settings.league_handle_lec
    parts = closing.split(" ")
    if not lec or lec in parts:
        return closing
    les = settings.league_handle_les
    if les in parts:
        parts.insert(parts.index(les) + 1, lec)
    else:
        parts.append(lec)
    return " ".join(parts)


class LeagueComparisonRequest(BaseModel):
    focus: str | None = None


class LeagueComparisonVariantResult(BaseModel):
    tone: str
    content: str | None = None
    char_count: int | None = None
    within_limit: bool | None = None
    suggested_teams: list[str] = []


@router.post("/league-comparison")
def generate_league_comparison(payload: LeagueComparisonRequest) -> list[LeagueComparisonVariantResult]:
    warm_stats_pages(
        team_tournaments=[None, get_lec_tournament()], player_tournaments=[None, get_lec_tournament()]
    )
    try:
        les_teams = fetch_team_stats()
        les_players = fetch_player_stats()
        lec_teams = fetch_team_stats(get_lec_tournament())
        lec_players = fetch_player_stats(get_lec_tournament())
        metric_candidates = compute_league_comparison_candidates(les_teams, les_players, lec_teams, lec_players)
    except GolGGError:
        metric_candidates = []  # degradacion elegante: seguimos con los cruces de jugadores igual

    try:
        crossover_candidates = compute_player_crossover_candidates()
    except CrossoverDataError:
        crossover_candidates = []

    candidates = metric_candidates + crossover_candidates
    if not candidates:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron obtener datos ni de gol.gg (LES/LEC) ni de la base de cruces de jugadores.",
        )

    try:
        candidate = pick_league_comparison_candidate(candidates, payload.focus)
    except StatFocusNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GolGGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    closing = _with_lec_handle(_closing_tags_for(candidate.kind, candidate.subject))
    # candidate.subject es un equipo (team_kda/team_winrate/team_fb) o un
    # jugador (player_kda/player_crossover) segun candidate.kind -- solo se
    # sugiere escudo cuando es un equipo, nunca se adivina para un jugador.
    suggested_teams = [candidate.subject] if candidate.kind.startswith("team_") else []

    return _generate_variants(
        ("sorprendente", "debate"),
        plain_fn=lambda tone: format_league_comparison_plain(candidate, tone),
        closing=closing,
        build_result=lambda tone, content, count, within: LeagueComparisonVariantResult(
            tone=tone,
            content=content,
            char_count=count,
            within_limit=within,
            suggested_teams=suggested_teams,
        ),
    )
