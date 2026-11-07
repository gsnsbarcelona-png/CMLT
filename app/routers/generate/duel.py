from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate._shared import TodayMatchInfo, _closing_tags_for, _generate_variants
from app.services.ai_service import generate_individual_duel_variant
from app.services.duel_service import compute_duel_candidates, reconcile_player_casing
from app.services.golgg_service import GolGGError, fetch_player_stats, format_stat_tweet_plain
from app.services.lolesports_service import (
    LoLEsportsError,
    TeamRosterNotFoundError,
    fetch_les_team_roster_with_roles,
    fetch_matches_today_or_tomorrow,
)

router = APIRouter()

DUEL_STYLES = {"plain", "ai"}


@router.get("/duel/today-match")
def get_duel_today_or_tomorrow_matches() -> list[TodayMatchInfo]:
    try:
        matches = fetch_matches_today_or_tomorrow(["les"])
    except LoLEsportsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [
        TodayMatchInfo(
            team_a=m.team1_name,
            team_b=m.team2_name,
            block_name=m.block_name,
            start_time=m.start_time.isoformat(),
        )
        for m in matches
    ]


class DuelGenerateRequest(BaseModel):
    team_a: str
    team_b: str
    style: str = "plain"


class DuelVariantResult(BaseModel):
    role: str
    subject: str
    content: str | None = None
    char_count: int | None = None
    within_limit: bool | None = None
    error: str | None = None
    suggested_teams: list[str] = []


@router.post("/duel")
def generate_duel(payload: DuelGenerateRequest) -> list[DuelVariantResult]:
    team_a = payload.team_a.strip()
    team_b = payload.team_b.strip()
    if not team_a or not team_b:
        raise HTTPException(status_code=400, detail="Elegi los dos equipos.")
    if team_a.lower() == team_b.lower():
        raise HTTPException(status_code=400, detail="Elegi dos equipos distintos.")

    style = payload.style.strip().lower()
    if style not in DUEL_STYLES:
        raise HTTPException(status_code=400, detail="Estilo no reconocido (usa 'plain' o 'ai').")

    try:
        roster_a = fetch_les_team_roster_with_roles(team_a)
        roster_b = fetch_les_team_roster_with_roles(team_b)
    except TeamRosterNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LoLEsportsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        player_stats = fetch_player_stats()
    except GolGGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # lolesports.com da los nombres en MAYUSCULAS; gol.gg tiene la
    # capitalizacion real -- se reconcilia antes de armar los duelos (mismo
    # patron que ya usa la comparacion de elo equipo vs equipo).
    known_players = [p.name for p in player_stats]
    for player in roster_a + roster_b:
        player.name = reconcile_player_casing([player.name], known_players)[0]

    candidates = compute_duel_candidates(roster_a, roster_b, player_stats)

    closing = _closing_tags_for("individual_duel", f"{team_a} vs {team_b}")

    return _generate_variants(
        candidates,
        style=style,
        ai_fn=lambda c: generate_individual_duel_variant(c.fact_sentence, c.subject),
        plain_fn=format_stat_tweet_plain,
        closing=closing,
        build_result=lambda c, content, count, within: DuelVariantResult(
            role=c.plano_title,
            subject=c.subject,
            content=content,
            char_count=count,
            within_limit=within,
            suggested_teams=[team_a, team_b],
        ),
        build_error_result=lambda c, error: DuelVariantResult(role=c.plano_title, subject=c.subject, error=error),
    )
