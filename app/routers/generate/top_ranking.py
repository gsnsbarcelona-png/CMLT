from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate._shared import _closing_tags_for, _generate_variants
from app.services.golgg_service import (
    TOP_RANKING_CATEGORIES,
    TOP_RANKING_CATEGORY_LABELS,
    GolGGError,
    compute_top_ranking_candidate,
    fetch_player_stats,
    fetch_team_stats,
    format_top_ranking_plain,
)

router = APIRouter()


class TopRankingGenerateRequest(BaseModel):
    category: str


class TopRankingVariantResult(BaseModel):
    variant: str
    content: str | None = None
    char_count: int | None = None
    within_limit: bool | None = None
    suggested_teams: list[str] = []


@router.get("/top-ranking/categories")
def list_top_ranking_categories() -> dict[str, str]:
    return TOP_RANKING_CATEGORY_LABELS


@router.post("/top-ranking")
def generate_top_ranking(payload: TopRankingGenerateRequest) -> list[TopRankingVariantResult]:
    category = payload.category.strip().lower()
    spec = TOP_RANKING_CATEGORIES.get(category)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"Categoria no reconocida: {category}.")

    try:
        team_stats = fetch_team_stats() if spec.level == "team" else []
        player_stats = fetch_player_stats() if spec.level == "player" else []
        candidate = compute_top_ranking_candidate(category, team_stats, player_stats)
    except GolGGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    leader = candidate.entries[0]
    closing = _closing_tags_for(candidate.kind, leader.name)
    # Solo se sugiere escudo cuando la categoria es de equipo -- gol.gg no da
    # el equipo de cada jugador, no se inventa para las categorias de jugador.
    suggested_teams = [leader.name] if candidate.level == "team" else []

    return _generate_variants(
        ("top1", "top3"),
        plain_fn=lambda variant: format_top_ranking_plain(candidate, variant),
        closing=closing,
        build_result=lambda variant, content, count, within: TopRankingVariantResult(
            variant=variant,
            content=content,
            char_count=count,
            within_limit=within,
            suggested_teams=suggested_teams,
        ),
    )
