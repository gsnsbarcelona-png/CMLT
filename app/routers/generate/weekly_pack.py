"""Pack semanal en un clic: calendario de la semana, resultados de la ultima
jornada, top de la semana y efemeride de hoy, todo de golpe. Reutiliza los
endpoints de generacion existentes (llamandolos como funciones, sin duplicar
su logica) y los ejecuta en paralelo. Tolerante a fallos parciales: una pieza
que falla (404 sin resultados, 502, ...) va con `error` y las demas siguen."""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate.anniversary import generate_anniversary
from app.routers.generate.calendar import CalendarGenerateRequest, generate_calendar
from app.routers.generate.results import ResultsGenerateRequest, generate_results
from app.routers.generate.top_ranking import TopRankingGenerateRequest, generate_top_ranking
from app.services.lolesports_service import LEAGUE_IDS

logger = logging.getLogger(__name__)

router = APIRouter()

# Categorias probadas en orden hasta que una tenga datos reales suficientes.
TOP_CATEGORY_ORDER = ("player_kda", "team_towers", "team_dragons", "team_fb", "player_csm", "team_fastest")


class WeeklyPackRequest(BaseModel):
    leagues: list[str] = ["les"]


class WeeklyPackItem(BaseModel):
    kind: str
    label: str
    content: str | None = None
    within_limit: bool | None = None
    char_count: int | None = None
    source: str = "weekly-pack"
    thread: list[str] = []
    card: dict | None = None
    suggested_teams: list[str] = []
    error: str | None = None


class WeeklyPackResponse(BaseModel):
    items: list[WeeklyPackItem]


def _from_result(kind: str, label: str, res: Any) -> WeeklyPackItem:
    return WeeklyPackItem(
        kind=kind,
        label=label,
        content=res.content,
        within_limit=res.within_limit,
        char_count=res.char_count,
        thread=getattr(res, "thread", []) or [],
        card=getattr(res, "card", None),
        suggested_teams=getattr(res, "suggested_teams", []) or [],
    )


def _calendar(leagues: list[str]) -> WeeklyPackItem:
    res = generate_calendar(CalendarGenerateRequest(leagues=leagues))
    return _from_result("calendar", "Calendario de la semana", res)


def _results(leagues: list[str]) -> WeeklyPackItem:
    res = generate_results(ResultsGenerateRequest(leagues=leagues))
    return _from_result("results", "Resultados de la última jornada", res)


def _top(leagues: list[str]) -> WeeklyPackItem:
    last_error = "No hay datos suficientes para un top."
    for category in TOP_CATEGORY_ORDER:
        try:
            variants = generate_top_ranking(TopRankingGenerateRequest(category=category))
        except HTTPException as exc:
            last_error = str(exc.detail)
            continue
        if not variants:
            continue
        best = next((v for v in variants if v.variant == "top3"), variants[0])
        return _from_result("top-ranking", "Top de la semana", best)
    raise HTTPException(status_code=502, detail=last_error)


def _anniversary(leagues: list[str]) -> WeeklyPackItem:
    variants = generate_anniversary()
    if not variants:
        raise HTTPException(status_code=404, detail="No hay efeméride para hoy.")
    best = next((v for v in variants if v.format == "completo"), variants[0])
    return _from_result("anniversary", "Efeméride de hoy", best)


_PIECES: tuple[tuple[str, str, Callable[[list[str]], WeeklyPackItem]], ...] = (
    ("calendar", "Calendario de la semana", _calendar),
    ("results", "Resultados de la última jornada", _results),
    ("top-ranking", "Top de la semana", _top),
    ("anniversary", "Efeméride de hoy", _anniversary),
)


def _run_piece(kind: str, label: str, fn: Callable[[list[str]], WeeklyPackItem], leagues: list[str]) -> WeeklyPackItem:
    try:
        return fn(leagues)
    except HTTPException as exc:
        return WeeklyPackItem(kind=kind, label=label, error=str(exc.detail))
    except Exception:  # una pieza rota no tumba el pack
        logger.exception("Pack semanal: fallo inesperado en %s", kind)
        return WeeklyPackItem(kind=kind, label=label, error="Error inesperado al generar esta pieza.")


@router.post("/weekly-pack")
def generate_weekly_pack(payload: WeeklyPackRequest | None = None) -> WeeklyPackResponse:
    leagues = [lg.strip().lower() for lg in (payload.leagues if payload else ["les"]) if lg.strip()] or ["les"]
    unknown = [lg for lg in leagues if lg not in LEAGUE_IDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Liga no reconocida: {', '.join(unknown)}.")

    with ThreadPoolExecutor(max_workers=len(_PIECES)) as pool:
        futures = [pool.submit(_run_piece, kind, label, fn, leagues) for kind, label, fn in _PIECES]
        items = [f.result() for f in futures]
    return WeeklyPackResponse(items=items)
