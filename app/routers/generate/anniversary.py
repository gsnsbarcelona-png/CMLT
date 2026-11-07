from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate._shared import _generate_variants
from app.services.history_service import (
    HistoryDataError,
    find_for_today,
    format_anniversary_plain,
    format_anniversary_quick_fact_plain,
)
from app.services.history_service import closing_tags as anniversary_closing_tags

router = APIRouter()


class AnniversaryVariantResult(BaseModel):
    format: str
    content: str | None = None
    char_count: int | None = None
    within_limit: bool | None = None
    is_exact: bool = False
    suggested_teams: list[str] = []


@router.post("/anniversary")
def generate_anniversary() -> list[AnniversaryVariantResult]:
    try:
        anniversary, is_exact, _days_away = find_for_today()
    except HistoryDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    closing = anniversary_closing_tags()

    formats = (
        ("completo", format_anniversary_plain),
        ("dato_rapido", format_anniversary_quick_fact_plain),
    )

    return _generate_variants(
        formats,
        plain_fn=lambda f: f[1](anniversary, is_exact),
        closing=closing,
        build_result=lambda f, content, count, within: AnniversaryVariantResult(
            format=f[0],
            content=content,
            char_count=count,
            within_limit=within,
            is_exact=is_exact,
            suggested_teams=anniversary.teams,
        ),
    )
