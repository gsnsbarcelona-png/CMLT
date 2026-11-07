from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate._shared import GenerateResult, _result
from app.services.lolesports_service import (
    LEAGUE_IDS,
    LoLEsportsError,
    closing_tags,
    fetch_latest_results,
    format_results_tweet,
    league_label,
)

router = APIRouter()


class ResultsGenerateRequest(BaseModel):
    leagues: list[str]


@router.post("/results")
def generate_results(payload: ResultsGenerateRequest) -> GenerateResult:
    leagues = [league.strip().lower() for league in payload.leagues if league.strip()]
    if not leagues:
        raise HTTPException(status_code=400, detail="Elige al menos una liga (LES, LEC o EMEA Masters).")
    unknown = [league for league in leagues if league not in LEAGUE_IDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Liga no reconocida: {', '.join(unknown)}.")

    try:
        results = fetch_latest_results(leagues)
    except LoLEsportsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No hay resultados de {league_label(leagues)} en los ultimos 7 dias.",
        )

    return _result(f"{format_results_tweet(results, leagues)}\n\n{closing_tags(leagues)}")
