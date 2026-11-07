import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.routers.generate._shared import GenerateResult, TodayMatchInfo, _closing_tags_for, _generate_variants, _result, _suggested_teams_for
from app.routers.images import IMAGES_DIR
from app.services.duel_service import reconcile_player_casing
from app.services.golgg_service import (
    GolGGError,
    StatFocusNotFoundError,
    aggregate_player_stats,
    aggregate_team_stats,
    build_head_to_head_preview,
    compute_candidates,
    compute_head_to_head_candidates,
    discover_tournaments,
    fetch_player_stats,
    fetch_team_stats,
    find_head_to_head,
    format_h2h_variant_plain,
    format_stat_tweet_plain,
    get_emea_masters_tournaments,
    warm_stats_pages,
    get_year_tournaments,
    pick_candidate,
    stat_closing_tags,
)
from app.services.image_service import ImageComposeError, compose_branded_image, compose_vs_image
from app.services.lolesports_service import (
    LoLEsportsError,
    TeamRosterNotFoundError,
    fetch_les_team_roster,
    fetch_todays_matches,
    get_les_team_logo_url,
    normalize_team_name,
)
from app.services.ranked_service import (
    RankedError,
    compute_player_vs_player_candidate,
    compute_rank_candidates,
    compute_team_vs_team_candidate,
    fetch_all_player_ranks,
)

router = APIRouter()

STAT_CATEGORIES = {"teams", "players", "ranked"}
STAT_SCOPES = {"split", "year"}
class StatGenerateRequest(BaseModel):
    categories: list[str] = []
    focus: str | None = None
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


@router.get("/stats/h2h-teams")
def list_h2h_teams() -> list[str]:
    """Lista de equipos seleccionables para H2H: LES + los que jugaron EMEA
    Masters en la temporada -- a diferencia de /stats/teams (solo LES, usado
    por el resto de los modos), aca hace falta poder elegir un rival de
    EMEA Masters que nunca jugo en LES."""
    emea_tournaments = get_emea_masters_tournaments()
    warm_stats_pages(team_tournaments=[None, *emea_tournaments])
    try:
        names = {t.name for t in fetch_team_stats()}
    except GolGGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    for tournament in emea_tournaments:
        try:
            names.update(t.name for t in fetch_team_stats(tournament))
        except GolGGError:
            continue  # best-effort: un torneo de EMEA Masters que falle no debe tumbar el resto

    return sorted(names)


@router.get("/team-logo")
def get_team_logo(team: str) -> dict:
    """Escudo de un equipo de LES (campo "image" de getTeams) para sugerir
    como imagen adjunta al tweet. Best-effort: 200 con image_url=None en vez
    de 404/502 si no matchea o falla lolesports.com -- es solo una sugerencia,
    nunca debe bloquear la generacion/guardado del tweet."""
    return {"image_url": get_les_team_logo_url(team)}


@router.get("/team-vs-logo")
def get_team_vs_logo(team_a: str, team_b: str) -> dict:
    """Composite "EquipoA VS EquipoB" armado con los escudos de ambos (ver
    image_service.compose_vs_image). A diferencia de /team-logo, aca SI se
    devuelve un error si algo falta -- un composite a medias (con un escudo
    generico o vacio) es peor que no ofrecer la opcion."""
    logo_a_url = get_les_team_logo_url(team_a)
    logo_b_url = get_les_team_logo_url(team_b)
    if not logo_a_url or not logo_b_url:
        missing = team_a if not logo_a_url else team_b
        raise HTTPException(status_code=404, detail=f"No encontramos el escudo de '{missing}'.")

    try:
        response_a = httpx.get(logo_a_url, timeout=10.0, follow_redirects=True)
        response_a.raise_for_status()
        response_b = httpx.get(logo_b_url, timeout=10.0, follow_redirects=True)
        response_b.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="No se pudieron descargar los escudos.") from exc

    try:
        composed = compose_vs_image(response_a.content, response_b.content)
    except ImageComposeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    (IMAGES_DIR / filename).write_bytes(composed)

    return {"image_url": f"/data/images/{filename}"}


@router.get("/branded-image")
def get_branded_image(team_a: str | None = None, team_b: str | None = None) -> dict:
    """Fondo de marca del programa con el logo chico abajo a la derecha (ver
    image_service.compose_branded_image) -- disponible siempre en el
    selector de imagen. Si se pasan uno o dos equipos (los sugeridos por la
    tarjeta), sus escudos se apilan arriba del logo de marca. Best-effort
    con los escudos: si alguno no se encuentra o no se puede descargar, la
    imagen se arma igual sin el (nunca bloquea el fondo de marca)."""
    team_logo_bytes_list = []
    for team in (team_a, team_b):
        if not team:
            continue
        logo_url = get_les_team_logo_url(team)
        if not logo_url:
            continue
        try:
            response = httpx.get(logo_url, timeout=10.0, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            continue
        team_logo_bytes_list.append(response.content)

    try:
        composed = compose_branded_image(team_logo_bytes_list)
    except ImageComposeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    (IMAGES_DIR / filename).write_bytes(composed)

    return {"image_url": f"/data/images/{filename}"}


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
        # fetch_all_player_ranks resuelve ambos en paralelo (mismo helper que ya
        # usa la comparacion equipo-vs-equipo, dos ramas mas abajo) en vez de dos
        # pedidos secuenciales a lolpros.gg.
        ranks, unresolved = fetch_all_player_ranks([ranked_player_a, ranked_player_b])
        if unresolved:
            raise HTTPException(
                status_code=400,
                detail=f"No encontramos datos de ranked para '{unresolved[0]}' en lolpros.gg.",
            )
        ranks_by_name = {r.player: r for r in ranks}
        candidate = compute_player_vs_player_candidate(
            ranks_by_name[ranked_player_a], ranks_by_name[ranked_player_b]
        )
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

        # Los dos equipos en paralelo (cada uno ya paraleliza sus jugadores).
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(fetch_all_player_ranks, roster_a)
            future_b = pool.submit(fetch_all_player_ranks, roster_b)
            ranks_a, _unresolved_a = future_a.result()
            ranks_b, _unresolved_b = future_b.result()
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
            # El angulo de rivalidad (head-to-head) combina el año completo por
            # diseño (ver README) -- solo tiene sentido sumarlo al pool cuando el
            # scope pedido es "year"; en "split" evita ~5 pedidos+parseos extra a
            # gol.gg que no aportan a un resultado scopeado al split actual.
            if "teams" in categories and scope == "year":
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

    content = f"{format_stat_tweet_plain(candidate)}\n\n{stat_closing_tags(candidate)}"
    return _result(content, _suggested_teams_for(candidate))


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


class HeadToHeadPreviewRequest(BaseModel):
    team_a: str
    team_b: str


class HeadToHeadVariantResult(BaseModel):
    angle: str
    content: str | None = None
    char_count: int | None = None
    within_limit: bool | None = None
    suggested_teams: list[str] = []


@router.post("/stats/head-to-head-preview")
def generate_head_to_head_preview(payload: HeadToHeadPreviewRequest) -> list[HeadToHeadVariantResult]:
    team_a = payload.team_a.strip()
    team_b = payload.team_b.strip()
    if not team_a or not team_b:
        raise HTTPException(status_code=400, detail="Elegi los dos equipos.")
    if team_a.lower() == team_b.lower():
        raise HTTPException(status_code=400, detail="Elegi dos equipos distintos.")

    # Se combinan los torneos de LES con los de EMEA Masters -- un equipo de
    # LES que juega ahi se cruza con rivales que nunca jugaron en LES, y sin
    # esto el historial/forma reciente de ese cruce queda siempre vacio.
    try:
        preview = build_head_to_head_preview(team_a, team_b, get_year_tournaments() + get_emea_masters_tournaments())
    except GolGGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # lolesports.com y gol.gg no usan exactamente el mismo nombre de equipo
    # (ej. "UCAM Esports" vs "UCAM Esports Club", "Barca eSports" vs "Barça
    # Esports" con tilde) -- se normaliza sacando acentos y se compara por
    # substring en vez de igualdad exacta.
    today_context = None
    try:
        wanted = {normalize_team_name(team_a), normalize_team_name(team_b)}
        for m in fetch_todays_matches(["les", "emea_masters"]):
            pair = {normalize_team_name(m.team1_name), normalize_team_name(m.team2_name)}
            if all(any(w in p or p in w for p in pair) for w in wanted):
                today_context = f"Partido de hoy: fase '{m.block_name}', horario {m.start_time:%H:%M} (Madrid)."
                break
    except LoLEsportsError:
        pass  # best-effort: si falla, seguimos sin ese contexto extra

    closing = _closing_tags_for("team_head_to_head", f"{team_a} vs {team_b}")

    return _generate_variants(
        ("historial", "forma_reciente"),
        plain_fn=lambda angle: format_h2h_variant_plain(preview, angle, today_context),
        closing=closing,
        build_result=lambda angle, content, count, within: HeadToHeadVariantResult(
            angle=angle,
            content=content,
            char_count=count,
            within_limit=within,
            suggested_teams=[team_a, team_b],
        ),
    )
