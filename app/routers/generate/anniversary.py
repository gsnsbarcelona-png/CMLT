from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate._shared import _generate_variants
from app.services.ai_service import generate_anniversary_quick_fact, generate_anniversary_tweet
from app.services.history_service import (
    HistoryDataError,
    find_for_today,
    format_anniversary_context,
    format_anniversary_plain,
    format_anniversary_quick_fact_plain,
)
from app.services.history_service import closing_tags as anniversary_closing_tags

router = APIRouter()

ANNIVERSARY_STYLES = {"plain", "ai"}


class AnniversaryGenerateRequest(BaseModel):
    style: str = "plain"


class AnniversaryVariantResult(BaseModel):
    format: str
    content: str | None = None
    char_count: int | None = None
    within_limit: bool | None = None
    error: str | None = None
    is_exact: bool = False
    suggested_teams: list[str] = []


@router.post("/anniversary")
def generate_anniversary(payload: AnniversaryGenerateRequest) -> list[AnniversaryVariantResult]:
    style = payload.style.strip().lower()
    if style not in ANNIVERSARY_STYLES:
        raise HTTPException(status_code=400, detail="Estilo no reconocido (usa 'plain' o 'ai').")

    try:
        anniversary, is_exact, _days_away = find_for_today()
    except HistoryDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    context = format_anniversary_context(anniversary, is_exact)
    closing = anniversary_closing_tags()

    formats = (
        ("completo", generate_anniversary_tweet, format_anniversary_plain),
        ("dato_rapido", generate_anniversary_quick_fact, format_anniversary_quick_fact_plain),
    )

    return _generate_variants(
        formats,
        style=style,
        ai_fn=lambda f: f[1](context),
        plain_fn=lambda f: f[2](anniversary, is_exact),
        closing=closing,
        build_result=lambda f, content, count, within: AnniversaryVariantResult(
            format=f[0],
            content=content,
            char_count=count,
            within_limit=within,
            is_exact=is_exact,
            suggested_teams=anniversary.teams,
        ),
        build_error_result=lambda f, error: AnniversaryVariantResult(format=f[0], error=error, is_exact=is_exact),
    )
