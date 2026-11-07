from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate._shared import GenerateResult, _result
from app.services.ai_service import AIGenerationError, generate_hype_calendar
from app.services.lolesports_service import (
    LEAGUE_IDS,
    LoLEsportsError,
    build_matches_context,
    closing_tags,
    fetch_upcoming_matches,
    format_schedule_tweet,
    league_label,
)

router = APIRouter()

CALENDAR_STYLES = {"plain", "hype"}


class CalendarGenerateRequest(BaseModel):
    leagues: list[str]
    style: str = "plain"


@router.post("/calendar")
def generate_calendar(payload: CalendarGenerateRequest) -> GenerateResult:
    leagues = [league.strip().lower() for league in payload.leagues if league.strip()]
    if not leagues:
        raise HTTPException(status_code=400, detail="Elegi al menos una liga (LES, LEC o EMEA Masters).")
    unknown = [league for league in leagues if league not in LEAGUE_IDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Liga no reconocida: {', '.join(unknown)}.")

    style = payload.style.strip().lower()
    if style not in CALENDAR_STYLES:
        raise HTTPException(status_code=400, detail="Estilo no reconocido (usa 'plain' o 'hype').")

    try:
        matches = fetch_upcoming_matches(leagues)
    except LoLEsportsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if style == "hype":
        try:
            content = generate_hype_calendar(build_matches_context(matches), league_label(leagues))
        except AIGenerationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        content = format_schedule_tweet(matches, leagues)

    content = f"{content}\n\n{closing_tags(leagues)}"
    return _result(content)
