from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate._shared import GenerateResult, _result
from app.services.lolesports_service import (
    LEAGUE_IDS,
    LoLEsportsError,
    closing_tags,
    fetch_upcoming_matches,
    format_schedule_tweet,
)

router = APIRouter()


class CalendarGenerateRequest(BaseModel):
    leagues: list[str]


@router.post("/calendar")
def generate_calendar(payload: CalendarGenerateRequest) -> GenerateResult:
    leagues = [league.strip().lower() for league in payload.leagues if league.strip()]
    if not leagues:
        raise HTTPException(status_code=400, detail="Elige al menos una liga (LES, LEC o EMEA Masters).")
    unknown = [league for league in leagues if league not in LEAGUE_IDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Liga no reconocida: {', '.join(unknown)}.")

    try:
        matches = fetch_upcoming_matches(leagues)
    except LoLEsportsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    content = f"{format_schedule_tweet(matches, leagues)}\n\n{closing_tags(leagues)}"
    return _result(content)
