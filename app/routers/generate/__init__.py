"""Router de /api/generate, partido en sub-routers por dominio (ver cada
archivo) para que ninguno crezca sin limite a medida que se suman modos
nuevos -- esto solo reorganiza donde vive el codigo, las rutas expuestas no
cambian (siguen bajo /api/generate, mismo prefijo y tags de siempre)."""

from fastapi import APIRouter

from app.routers.generate import (
    anniversary,
    calendar,
    duel,
    league_comparison,
    results,
    stats,
    top_ranking,
)

router = APIRouter(prefix="/api/generate", tags=["generate"])
router.include_router(calendar.router)
router.include_router(results.router)
router.include_router(stats.router)
router.include_router(duel.router)
router.include_router(anniversary.router)
router.include_router(league_comparison.router)
router.include_router(top_ranking.router)
