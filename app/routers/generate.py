from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.models import Template
from app.routers.templates import render_template
from app.services import char_count
from app.services.ai_service import (
    AIGenerationError,
    generate_anniversary_quick_fact,
    generate_anniversary_tweet,
    generate_head_to_head_variant,
    generate_hype_calendar,
    generate_individual_duel_variant,
    generate_league_comparison_variant,
    generate_stat_tweet,
    generate_tweet,
)
from app.services.crossover_service import CrossoverDataError, compute_player_crossover_candidates
from app.services.duel_service import compute_duel_candidates, reconcile_player_casing
from app.services.golgg_service import (
    GolGGError,
    StatCandidate,
    StatFocusNotFoundError,
    aggregate_player_stats,
    aggregate_team_stats,
    build_head_to_head_preview,
    compute_candidates,
    compute_head_to_head_candidates,
    compute_league_comparison_candidates,
    discover_tournaments,
    fetch_player_stats,
    fetch_team_stats,
    find_head_to_head,
    format_h2h_context,
    format_h2h_variant_plain,
    format_league_comparison_context,
    format_league_comparison_plain,
    format_stat_tweet_plain,
    get_lec_tournament,
    get_year_tournaments,
    pick_candidate,
    pick_league_comparison_candidate,
    stat_closing_tags,
)
from app.services.history_service import (
    HistoryDataError,
    find_for_today,
    format_anniversary_context,
    format_anniversary_plain,
    format_anniversary_quick_fact_plain,
)
from app.services.history_service import closing_tags as anniversary_closing_tags
from app.services.lolesports_service import (
    LEAGUE_IDS,
    LoLEsportsError,
    TeamRosterNotFoundError,
    build_matches_context,
    closing_tags,
    fetch_les_team_roster,
    fetch_les_team_roster_with_roles,
    fetch_matches_today_or_tomorrow,
    fetch_todays_matches,
    fetch_upcoming_matches,
    format_schedule_tweet,
    league_label,
    normalize_team_name,
)
from app.services.ranked_service import (
    RankedError,
    compute_player_vs_player_candidate,
    compute_rank_candidates,
    compute_team_vs_team_candidate,
    fetch_all_player_ranks,
    fetch_player_rank,
)

CALENDAR_STYLES = {"plain", "hype"}
STAT_CATEGORIES = {"teams", "players", "ranked"}
STAT_STYLES = {"plain", "ai"}
STAT_SCOPES = {"split", "year"}

router = APIRouter(prefix="/api/generate", tags=["generate"])

MAX_BATCH_TOPICS = 25


class GenerateResult(BaseModel):
    content: str
    char_count: int
    within_limit: bool


def _result(content: str) -> GenerateResult:
    count = char_count.count_chars(content)
    return GenerateResult(content=content, char_count=count, within_limit=count <= char_count.TWEET_CHAR_LIMIT)


class AIGenerateRequest(BaseModel):
    topic: str
    tone: str | None = None
    instructions: str | None = None


@router.post("/ai")
def generate_ai(payload: AIGenerateRequest) -> GenerateResult:
    try:
        content = generate_tweet(payload.topic, payload.tone, payload.instructions)
    except AIGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _result(content)


class BatchGenerateRequest(BaseModel):
    topics: list[str]
    tone: str | None = None
    instructions: str | None = None


class BatchTopicResult(BaseModel):
    topic: str
    content: str | None = None
    char_count: int | None = None
    within_limit: bool | None = None
    error: str | None = None


@router.post("/ai/batch")
def generate_ai_batch(payload: BatchGenerateRequest) -> list[BatchTopicResult]:
    topics = [t.strip() for t in payload.topics if t.strip()]
    if not topics:
        raise HTTPException(status_code=400, detail="Ingresa al menos un tema.")
    if len(topics) > MAX_BATCH_TOPICS:
        raise HTTPException(status_code=400, detail=f"Maximo {MAX_BATCH_TOPICS} temas por lote.")

    results: list[BatchTopicResult] = []
    for topic in topics:
        try:
            content = generate_tweet(topic, payload.tone, payload.instructions)
        except AIGenerationError as exc:
            results.append(BatchTopicResult(topic=topic, error=str(exc)))
            continue

        count = char_count.count_chars(content)
        results.append(
            BatchTopicResult(
                topic=topic,
                content=content,
                char_count=count,
                within_limit=count <= char_count.TWEET_CHAR_LIMIT,
            )
        )
    return results


class CalendarGenerateRequest(BaseModel):
    leagues: list[str]
    style: str = "plain"


@router.post("/calendar")
def generate_calendar(payload: CalendarGenerateRequest) -> GenerateResult:
    leagues = [league.strip().lower() for league in payload.leagues if league.strip()]
    if not leagues:
        raise HTTPException(status_code=400, detail="Elegi al menos una liga (LES o LEC).")
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


class StatGenerateRequest(BaseModel):
    categories: list[str] = []
    focus: str | None = None
    style: str = "plain"
    scope: str = "split"
    rivalry_team_a: str | None = None
    rivalry_team_b: str | None = None
    ranked_player_a: str | None = None
    ranked_player_b: str | None = None
    ranked_team_a: str | None = None
    ranked_team_b: str | None = None


@router.get("/stats/teams")
def list_stat_teams() -> list[str]:
    try:
        teams = fetch_team_stats()
    except GolGGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return sorted(t.name for t in teams)


@router.get("/stats/available-tournaments")
def list_available_tournaments(season: str | None = None, region: str | None = "ES") -> list[dict]:
    """Herramienta de mantenimiento: lista los torneos de gol.gg para una
    temporada/region (por defecto ES), asi se puede encontrar el nombre
    exacto de un torneo nuevo (ej. al arrancar un split) sin buscarlo a mano."""
    try:
        return discover_tournaments(season, region)
    except GolGGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/stats")
def generate_stats(payload: StatGenerateRequest) -> GenerateResult:
    style = payload.style.strip().lower()
    if style not in STAT_STYLES:
        raise HTTPException(status_code=400, detail="Estilo no reconocido (usa 'plain' o 'ai').")

    rivalry_a = (payload.rivalry_team_a or "").strip()
    rivalry_b = (payload.rivalry_team_b or "").strip()
    ranked_player_a = (payload.ranked_player_a or "").strip()
    ranked_player_b = (payload.ranked_player_b or "").strip()
    ranked_team_a = (payload.ranked_team_a or "").strip()
    ranked_team_b = (payload.ranked_team_b or "").strip()

    if rivalry_a or rivalry_b:
        if not (rivalry_a and rivalry_b):
            raise HTTPException(status_code=400, detail="Elegi los dos equipos para ver su rivalidad.")
        try:
            candidate = find_head_to_head(rivalry_a, rivalry_b, get_year_tournaments())
        except GolGGError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if candidate is None:
            raise HTTPException(
                status_code=400,
                detail=f"No encontramos cruces entre '{rivalry_a}' y '{rivalry_b}' en la temporada.",
            )
    elif ranked_player_a or ranked_player_b:
        if not (ranked_player_a and ranked_player_b):
            raise HTTPException(status_code=400, detail="Elegi los dos jugadores para comparar su elo.")
        if ranked_player_a.lower() == ranked_player_b.lower():
            raise HTTPException(status_code=400, detail="Elegi dos jugadores distintos.")
        try:
            rank_a = fetch_player_rank(ranked_player_a)
            rank_b = fetch_player_rank(ranked_player_b)
        except RankedError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        missing = [n for n, r in ((ranked_player_a, rank_a), (ranked_player_b, rank_b)) if r is None]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"No encontramos datos de ranked para '{missing[0]}' en lolpros.gg.",
            )
        candidate = compute_player_vs_player_candidate(rank_a, rank_b)
    elif ranked_team_a or ranked_team_b:
        if not (ranked_team_a and ranked_team_b):
            raise HTTPException(status_code=400, detail="Elegi los dos equipos para comparar su elo.")
        if ranked_team_a.lower() == ranked_team_b.lower():
            raise HTTPException(status_code=400, detail="Elegi dos equipos distintos.")
        try:
            roster_a = fetch_les_team_roster(ranked_team_a)
            roster_b = fetch_les_team_roster(ranked_team_b)
        except TeamRosterNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LoLEsportsError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        try:
            known_players = [p.name for p in fetch_player_stats()]
        except GolGGError:
            known_players = []  # degradacion elegante: sigue andando, solo sin la capitalizacion "linda"
        roster_a = reconcile_player_casing(roster_a, known_players)
        roster_b = reconcile_player_casing(roster_b, known_players)

        ranks_a, _unresolved_a = fetch_all_player_ranks(roster_a)
        ranks_b, _unresolved_b = fetch_all_player_ranks(roster_b)
        try:
            candidate = compute_team_vs_team_candidate(ranked_team_a, ranked_team_b, ranks_a, ranks_b)
        except RankedError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        categories = {c.strip().lower() for c in payload.categories if c.strip()}
        if not categories:
            raise HTTPException(
                status_code=400, detail="Elegi al menos una categoria (equipos, jugadores o ranked)."
            )
        unknown = categories - STAT_CATEGORIES
        if unknown:
            raise HTTPException(status_code=400, detail=f"Categoria no reconocida: {', '.join(unknown)}.")

        scope = payload.scope.strip().lower()
        if scope not in STAT_SCOPES:
            raise HTTPException(status_code=400, detail="Alcance no reconocido (usa 'split' o 'year').")

        try:
            if scope == "year":
                year_tournaments = get_year_tournaments()
                team_stats = aggregate_team_stats(year_tournaments) if "teams" in categories else []
                player_stats = aggregate_player_stats(year_tournaments) if "players" in categories else []
            else:
                team_stats = fetch_team_stats() if "teams" in categories else []
                player_stats = fetch_player_stats() if "players" in categories else []

            candidates = compute_candidates(team_stats, player_stats, categories)
            if "teams" in categories:
                candidates += compute_head_to_head_candidates(get_year_tournaments())
            if "ranked" in categories:
                # El rango de SoloQ no tiene "scope" (siempre es el estado
                # actual) -- reusa el roster ya pedido si esta disponible,
                # si no pide el del split actual solo para tener los nombres.
                roster = player_stats if player_stats else fetch_player_stats()
                ranks, _unresolved = fetch_all_player_ranks([p.name for p in roster])
                candidates += compute_rank_candidates(ranks)
        except GolGGError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except RankedError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        try:
            candidate = pick_candidate(candidates, payload.focus)
        except StatFocusNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except GolGGError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    if style == "ai":
        try:
            content = generate_stat_tweet(candidate.fact_sentence, candidate.subject)
        except AIGenerationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        content = format_stat_tweet_plain(candidate)

    content = f"{content}\n\n{stat_closing_tags(candidate)}"
    return _result(content)


class TodayMatchInfo(BaseModel):
    team_a: str
    team_b: str
    block_name: str
    start_time: str


@router.get("/stats/today-match")
def get_todays_matches() -> list[TodayMatchInfo]:
    try:
        matches = fetch_todays_matches(["les"])
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


HEAD_TO_HEAD_STYLES = {"plain", "ai"}


class HeadToHeadPreviewRequest(BaseModel):
    team_a: str
    team_b: str
    style: str = "plain"


class HeadToHeadVariantResult(BaseModel):
    angle: str
    content: str | None = None
    char_count: int | None = None
    within_limit: bool | None = None
    error: str | None = None


@router.post("/stats/head-to-head-preview")
def generate_head_to_head_preview(payload: HeadToHeadPreviewRequest) -> list[HeadToHeadVariantResult]:
    team_a = payload.team_a.strip()
    team_b = payload.team_b.strip()
    if not team_a or not team_b:
        raise HTTPException(status_code=400, detail="Elegi los dos equipos.")
    if team_a.lower() == team_b.lower():
        raise HTTPException(status_code=400, detail="Elegi dos equipos distintos.")

    style = payload.style.strip().lower()
    if style not in HEAD_TO_HEAD_STYLES:
        raise HTTPException(status_code=400, detail="Estilo no reconocido (usa 'plain' o 'ai').")

    try:
        preview = build_head_to_head_preview(team_a, team_b, get_year_tournaments())
    except GolGGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # lolesports.com y gol.gg no usan exactamente el mismo nombre de equipo
    # (ej. "UCAM Esports" vs "UCAM Esports Club", "Barca eSports" vs "Barça
    # Esports" con tilde) -- se normaliza sacando acentos y se compara por
    # substring en vez de igualdad exacta.
    today_context = None
    try:
        wanted = {normalize_team_name(team_a), normalize_team_name(team_b)}
        for m in fetch_todays_matches(["les"]):
            pair = {normalize_team_name(m.team1_name), normalize_team_name(m.team2_name)}
            if all(any(w in p or p in w for p in pair) for w in wanted):
                today_context = f"Partido de hoy: fase '{m.block_name}', horario {m.start_time:%H:%M} (Madrid)."
                break
    except LoLEsportsError:
        pass  # best-effort: si falla, seguimos sin ese contexto extra

    context = format_h2h_context(preview, today_context)
    closing = stat_closing_tags(
        StatCandidate(
            kind="team_head_to_head",
            subject=f"{team_a} vs {team_b}",
            fact_sentence="",
            plano_emoji="",
            plano_title="",
            plano_question="",
        )
    )

    results: list[HeadToHeadVariantResult] = []
    for angle_key, angle_label in (("historial", "historial"), ("forma_reciente", "forma reciente")):
        if style == "ai":
            try:
                content = generate_head_to_head_variant(context, angle_label)
            except AIGenerationError as exc:
                results.append(HeadToHeadVariantResult(angle=angle_key, error=str(exc)))
                continue
        else:
            content = format_h2h_variant_plain(preview, angle_key, today_context)

        content = f"{content}\n\n{closing}"
        count = char_count.count_chars(content)
        results.append(
            HeadToHeadVariantResult(
                angle=angle_key,
                content=content,
                char_count=count,
                within_limit=count <= char_count.TWEET_CHAR_LIMIT,
            )
        )
    return results


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


DUEL_STYLES = {"plain", "ai"}


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

    closing = stat_closing_tags(
        StatCandidate(
            kind="individual_duel",
            subject=f"{team_a} vs {team_b}",
            fact_sentence="",
            plano_emoji="",
            plano_title="",
            plano_question="",
        )
    )

    results: list[DuelVariantResult] = []
    for candidate in candidates:
        if style == "ai":
            try:
                content = generate_individual_duel_variant(candidate.fact_sentence, candidate.subject)
            except AIGenerationError as exc:
                results.append(
                    DuelVariantResult(role=candidate.plano_title, subject=candidate.subject, error=str(exc))
                )
                continue
        else:
            content = format_stat_tweet_plain(candidate)

        content = f"{content}\n\n{closing}"
        count = char_count.count_chars(content)
        results.append(
            DuelVariantResult(
                role=candidate.plano_title,
                subject=candidate.subject,
                content=content,
                char_count=count,
                within_limit=count <= char_count.TWEET_CHAR_LIMIT,
            )
        )
    return results


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

    results: list[AnniversaryVariantResult] = []
    for format_key, ai_fn, plain_fn in formats:
        if style == "ai":
            try:
                content = ai_fn(context)
            except AIGenerationError as exc:
                results.append(AnniversaryVariantResult(format=format_key, error=str(exc), is_exact=is_exact))
                continue
        else:
            content = plain_fn(anniversary, is_exact)

        content = f"{content}\n\n{closing}"
        count = char_count.count_chars(content)
        results.append(
            AnniversaryVariantResult(
                format=format_key,
                content=content,
                char_count=count,
                within_limit=count <= char_count.TWEET_CHAR_LIMIT,
                is_exact=is_exact,
            )
        )
    return results


LEAGUE_COMPARISON_STYLES = {"plain", "ai"}


class LeagueComparisonRequest(BaseModel):
    style: str = "plain"
    focus: str | None = None


class LeagueComparisonVariantResult(BaseModel):
    tone: str
    content: str | None = None
    char_count: int | None = None
    within_limit: bool | None = None
    error: str | None = None


@router.post("/league-comparison")
def generate_league_comparison(payload: LeagueComparisonRequest) -> list[LeagueComparisonVariantResult]:
    style = payload.style.strip().lower()
    if style not in LEAGUE_COMPARISON_STYLES:
        raise HTTPException(status_code=400, detail="Estilo no reconocido (usa 'plain' o 'ai').")

    try:
        les_teams = fetch_team_stats()
        les_players = fetch_player_stats()
        lec_teams = fetch_team_stats(get_lec_tournament())
        lec_players = fetch_player_stats(get_lec_tournament())
        metric_candidates = compute_league_comparison_candidates(les_teams, les_players, lec_teams, lec_players)
    except GolGGError:
        metric_candidates = []  # degradacion elegante: seguimos con los cruces de jugadores igual

    try:
        crossover_candidates = compute_player_crossover_candidates()
    except CrossoverDataError:
        crossover_candidates = []

    candidates = metric_candidates + crossover_candidates
    if not candidates:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron obtener datos ni de gol.gg (LES/LEC) ni de la base de cruces de jugadores.",
        )

    try:
        candidate = pick_league_comparison_candidate(candidates, payload.focus)
    except StatFocusNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GolGGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    closing = stat_closing_tags(
        StatCandidate(
            kind=candidate.kind,
            subject=candidate.subject,
            fact_sentence="",
            plano_emoji="",
            plano_title="",
            plano_question="",
        )
    )

    results: list[LeagueComparisonVariantResult] = []
    for tone in ("sorprendente", "debate"):
        if style == "ai":
            try:
                content = generate_league_comparison_variant(format_league_comparison_context(candidate, tone))
            except AIGenerationError as exc:
                results.append(LeagueComparisonVariantResult(tone=tone, error=str(exc)))
                continue
        else:
            content = format_league_comparison_plain(candidate, tone)

        content = f"{content}\n\n{closing}"
        count = char_count.count_chars(content)
        results.append(
            LeagueComparisonVariantResult(
                tone=tone,
                content=content,
                char_count=count,
                within_limit=count <= char_count.TWEET_CHAR_LIMIT,
            )
        )
    return results


class TemplateGenerateRequest(BaseModel):
    template_id: int
    variables: dict[str, str] = {}


@router.post("/template")
def generate_from_template(
    payload: TemplateGenerateRequest, session: Session = Depends(get_session)
) -> GenerateResult:
    template = session.get(Template, payload.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    try:
        content = render_template(template.template_text, payload.variables)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _result(content)
