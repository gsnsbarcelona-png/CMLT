"""Helpers compartidos por los sub-routers de /api/generate (ver
app/routers/generate/__init__.py): construccion de GenerateResult, sugerencia
de escudos, cierre de arrobas/hashtags para candidatos sinteticos y el patron
de "variante con IA + fallback a texto plano" que reusan H2H, Duelo,
Efemeride, Cruce LEC y Top/Ranking. Nada de esto es especifico de un dominio
-- por eso vive aca en vez de en cualquiera de los sub-routers."""

from typing import Any, Callable, Iterable

from pydantic import BaseModel

from app.services import char_count
from app.services.ai_service import AIGenerationError
from app.services.golgg_service import TEAM_LEVEL_KINDS, StatCandidate, stat_closing_tags


class GenerateResult(BaseModel):
    content: str
    char_count: int
    within_limit: bool
    suggested_teams: list[str] = []


class TodayMatchInfo(BaseModel):
    """Forma compartida por /stats/today-match (stats.py) y /duel/today-match
    (duel.py) -- mismo shape, distinta fuente (hoy vs hoy/manana)."""

    team_a: str
    team_b: str
    block_name: str
    start_time: str


def _result(content: str, suggested_teams: list[str] | None = None) -> GenerateResult:
    count = char_count.count_chars(content)
    return GenerateResult(
        content=content,
        char_count=count,
        within_limit=count <= char_count.TWEET_CHAR_LIMIT,
        suggested_teams=suggested_teams or [],
    )


def _suggested_teams_for(candidate: StatCandidate) -> list[str]:
    """Mismo criterio que TEAM_LEVEL_KINDS ya usa para decidir si arrobar
    equipo(s) en el cierre -- si el candidato es de nivel equipo, su subject
    ya es "Equipo" o "EquipoA vs EquipoB", exactamente lo que hace falta para
    sugerir escudo(s). No se sugiere nada para candidatos de jugador."""
    if candidate.kind not in TEAM_LEVEL_KINDS:
        return []
    return [n.strip() for n in candidate.subject.split(" vs ")]


def _closing_tags_for(kind: str, subject: str) -> str:
    """Arrobas/hashtags de cierre para un `kind`/`subject` puntual, sin tener
    un StatCandidate real a mano (H2H, Duelo, Cruce LEC, Top/Ranking arman el
    contenido por su cuenta y solo necesitan stat_closing_tags() para el
    cierre) -- evita repetir el StatCandidate sintetico vacio en cada uno."""
    return stat_closing_tags(
        StatCandidate(kind=kind, subject=subject, fact_sentence="", plano_emoji="", plano_title="", plano_question="")
    )


def _generate_variants(
    items: Iterable[Any],
    *,
    style: str,
    ai_fn: Callable[[Any], str],
    plain_fn: Callable[[Any], str],
    closing: str,
    build_result: Callable[[Any, str, int, bool], Any],
    build_error_result: Callable[[Any, str], Any],
) -> list:
    """Patron compartido por H2H, Duelo, Efemeride, Cruce LEC y Top/Ranking:
    para cada `item` de una tanda ya calculada (un angulo, un candidato, un
    tono...), generar el contenido -- con IA (con fallback a una tarjeta de
    error individual si falla) o en texto plano --, pegarle `closing`,
    contar caracteres y armar el resultado tipado de cada endpoint via
    `build_result`/`build_error_result` (que solo conocen la forma del
    modelo Pydantic de ese endpoint, no la logica de generacion)."""
    results = []
    for item in items:
        if style == "ai":
            try:
                content = ai_fn(item)
            except AIGenerationError as exc:
                results.append(build_error_result(item, str(exc)))
                continue
        else:
            content = plain_fn(item)

        content = f"{content}\n\n{closing}"
        count = char_count.count_chars(content)
        results.append(build_result(item, content, count, count <= char_count.TWEET_CHAR_LIMIT))
    return results
