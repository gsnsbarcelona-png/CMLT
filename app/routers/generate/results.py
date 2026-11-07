from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate._shared import GenerateResult, _result
from app.services import char_count
from app.services.lolesports_service import (
    LEAGUE_IDS,
    LoLEsportsError,
    closing_tags,
    fetch_latest_results,
    format_results_thread,
    format_results_tweet,
    league_label,
)

router = APIRouter()


class ResultsGenerateRequest(BaseModel):
    leagues: list[str]


class ResultsGenerateResult(GenerateResult):
    # Opcional: solo viene relleno si los resultados no caben en un tweet;
    # entonces `content` va recortado y `thread` trae todos los partidos.
    thread: list[str] = []


@router.post("/results")
def generate_results(payload: ResultsGenerateRequest) -> ResultsGenerateResult:
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
            detail=f"No hay resultados de {league_label(leagues)} en los últimos 7 días.",
        )

    card = {
        "kind": "results",
        "title": f"Resultados {league_label(leagues)}"[:60],
        "subtitle": f"Jornada del {results[0].start_time:%d/%m/%Y}",
        "matches": [
            {
                "team1": r.team1_name[:40] or r.team1_code,
                "team2": r.team2_name[:40] or r.team2_code,
                "score1": min(r.score1, 99),
                "score2": min(r.score2, 99),
                "block": (r.block_name or "")[:40],
            }
            for r in results[:12]
        ],
    }
    closing = closing_tags(leagues)
    full = f"{format_results_tweet(results, leagues)}\n\n{closing}"
    if char_count.count_chars(full) <= char_count.TWEET_CHAR_LIMIT:
        return ResultsGenerateResult(**_result(full).model_dump(exclude={"card"}), card=card)

    # No caben todos los partidos: el contenido se recorta con "...y X partidos
    # mas" (cabe en 280, con el cierre) y `thread` trae todos, uno a uno.
    budget = char_count.TWEET_CHAR_LIMIT - len(closing) - 2
    trimmed = f"{format_results_tweet(results, leagues, max_chars=budget)}\n\n{closing}"
    return ResultsGenerateResult(
        **_result(trimmed).model_dump(exclude={"card"}),
        card=card,
        thread=format_results_thread(results, leagues, closing),
    )
