"""Sugerencia del dia: que toca hoy en Compose, calculado con el calendario
real de LoL Esports. Nunca falla: si la API cae devuelve lista vacia + error."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models import Tweet
from app.services import lolesports_service as lol
from app.services.history_service import HistoryDataError, find_for_date

logger = logging.getLogger("app")
router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])

MAX_SUGGESTIONS = 4
RESULTS_WINDOW_HOURS = 36
LES = ["les"]


def _has_tweeted_results(session: Session, since: datetime) -> bool:
    """Hay algun tweet de Resultados (borrador o publicado) creado desde `since`."""
    rows = session.exec(select(Tweet.created_at).where(Tweet.source == "results")).all()
    for created in rows:
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created >= since:
            return True
    return False


def _real(m: lol.MatchInfo) -> bool:
    return "TBD" not in (m.team1_name, m.team2_name)


def build_suggestions(session: Session, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(lol.MADRID_TZ).date()
    tomorrow = today + timedelta(days=1)
    out: list[dict] = []

    matches = lol.fetch_upcoming_matches(LES, now=now)
    todays = [m for m in matches if m.start_time.date() == today]
    tomorrows = [m for m in matches if m.start_time.date() == tomorrow]

    for m in [m for m in todays if _real(m)][:2]:
        out.append({
            "kind": "h2h",
            "title": f"Hoy juega {m.team1_name} vs {m.team2_name}",
            "detail": "Haz la previa H2H",
            "mode": "h2h",
            "params": {"team_a": m.team1_name, "team_b": m.team2_name},
        })
    if todays:
        n = len(todays)
        out.append({
            "kind": "match-day",
            "title": "Día de partido",
            "detail": f"{n} partido{'s' if n != 1 else ''} de LES hoy",
            "mode": "match-day",
            "params": {},
        })

    try:
        results = lol.fetch_latest_results(LES, now=now, lookback_days=2)
    except lol.LoLEsportsError:
        results = []
    cutoff = now - timedelta(hours=RESULTS_WINDOW_HOURS)
    recent = [r for r in results if r.start_time.astimezone(timezone.utc) >= cutoff]
    if recent and not _has_tweeted_results(session, max(r.start_time for r in recent).astimezone(timezone.utc)):
        n = len(recent)
        plural = "partidos" if n != 1 else "partido"
        when = "Ayer" if recent[0].start_time.date() < today else "Hoy"
        verb = "hubo" if when == "Ayer" else "ha habido"
        out.append({
            "kind": "results",
            "title": f"{when} {verb} {n} {plural}",
            "detail": "Saca los resultados",
            "mode": "results",
            "params": {},
        })

    real_tomorrow = [m for m in tomorrows if _real(m)]
    if real_tomorrow:
        m = real_tomorrow[0]
        out.append({
            "kind": "calendar",
            "title": f"Mañana juega {m.team1_name} vs {m.team2_name}",
            "detail": "Prepara el calendario",
            "mode": "calendar",
            "params": {},
        })

    if not out:
        try:
            anniv = find_for_date(today.month, today.day)
        except HistoryDataError:
            anniv = None
        if anniv is not None:
            out.append({
                "kind": "anniversary",
                "title": f"Efeméride de hoy: {anniv.headline}",
                "detail": f"{anniv.year}",
                "mode": "anniversary",
                "params": {},
            })
        else:
            out.append({
                "kind": "empty",
                "title": "Sin partidos hoy",
                "detail": "Nada urgente: prueba Stats o Top/Ranking",
                "mode": "",
                "params": {},
            })
    return out[:MAX_SUGGESTIONS]


@router.get("/today")
def suggestions_today(session: Session = Depends(get_session)) -> dict:
    try:
        return {"suggestions": build_suggestions(session)}
    except Exception as exc:  # nunca falla: la sugerencia es un extra
        logger.warning("Sugerencias del día fallaron: %s", exc)
        return {"suggestions": [], "error": "No se pudo consultar el calendario."}
