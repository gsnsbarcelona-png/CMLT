import json
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.config import settings
from app.services.phrasing import vary_question
from app.services import char_count

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "les_anniversaries.json"


class HistoryDataError(Exception):
    pass


@dataclass
class Anniversary:
    month: int
    day: int
    year: int
    headline: str
    detail: str
    era_name: str
    teams: list[str]
    today_connection: str | None
    source: str


def load_anniversaries() -> list[Anniversary]:
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoryDataError(f"No se pudo leer la base de efemerides ({DATA_PATH}).") from exc

    return [
        Anniversary(
            month=entry["month"],
            day=entry["day"],
            year=entry["year"],
            headline=entry["headline"],
            detail=entry["detail"],
            era_name=entry["era_name"],
            teams=entry.get("teams") or [],
            today_connection=entry.get("today_connection"),
            source=entry.get("source", ""),
        )
        for entry in raw
    ]


def _day_of_year(month: int, day: int) -> int:
    # Año de referencia no bisiesto -- ninguna entrada usa 29/02, asi que es seguro.
    return date(2001, month, day).timetuple().tm_yday


def find_for_date(month: int, day: int) -> Anniversary | None:
    matches = [a for a in load_anniversaries() if a.month == month and a.day == day]
    if not matches:
        return None
    return random.choice(matches)


def find_nearest(month: int, day: int) -> tuple[Anniversary, int] | None:
    """Devuelve (efemeride, dias_de_distancia) mas cercana en el calendario
    (con wraparound de fin/inicio de año), o None si la base esta vacia."""
    anniversaries = load_anniversaries()
    if not anniversaries:
        return None

    target = _day_of_year(month, day)

    def distance(a: Anniversary) -> int:
        diff = abs(_day_of_year(a.month, a.day) - target)
        return min(diff, 365 - diff)

    best = min(anniversaries, key=distance)
    return best, distance(best)


def find_for_today(today: date | None = None) -> tuple[Anniversary, bool, int]:
    """(efemeride, es_de_hoy_exacto, dias_de_distancia). Si no hay ninguna
    efemeride cargada, levanta HistoryDataError."""
    if today is None:
        today = date.today()

    exact = find_for_date(today.month, today.day)
    if exact is not None:
        return exact, True, 0

    nearest = find_nearest(today.month, today.day)
    if nearest is None:
        raise HistoryDataError("No hay ninguna efemeride cargada todavia en la base.")
    anniversary, days_away = nearest
    return anniversary, False, days_away




def _truncate(text: str, budget: int) -> str:
    """Recorta text a como mucho budget caracteres (sin URLs de por medio,
    asi que contar es simplemente len()), cortando en el ultimo espacio
    razonable para no partir una palabra a la mitad."""
    if budget <= 0:
        return ""
    if len(text) <= budget:
        return text
    cut = text[: max(budget - 1, 0)]
    last_space = cut.rfind(" ")
    if last_space > budget * 0.6:  # no cortar si perderiamos demasiado texto
        cut = cut[:last_space]
    return cut.rstrip(" .,;:-") + "…"


def format_anniversary_plain(anniversary: Anniversary, is_exact: bool, today: date | None = None) -> str:
    if today is None:
        today = date.today()
    years_ago = today.year - anniversary.year

    if is_exact:
        header = f"🗓️ UN DIA COMO HOY, hace {years_ago} años ({anniversary.year})"
    else:
        header = (
            f"🗓️ No es de hoy exacto -- lo mas cercano: {anniversary.day:02d}/{anniversary.month:02d}/"
            f"{anniversary.year} (hace {years_ago} años)"
        )
    question = vary_question("¿Lo viviste en directo?") + " 👀"

    # El cierre (arrobas/hashtags) lo agrega el router despues de esta
    # funcion, pero hay que reservarle presupuesto aca: lo unico que puede
    # desbordar 280 es el "cuerpo" (hecho + detalle + conexion con hoy),
    # texto libre de una base curada que va a seguir creciendo -- se recorta
    # con "…" si hace falta para garantizar que el tweet final nunca se pase
    # del limite, sea cual sea el largo del dato cargado.
    reserved = (
        char_count.count_chars(header)
        + 2  # saltos de linea: encabezado->cuerpo y cuerpo->pregunta
        + char_count.count_chars(question)
        + 2  # "\n\n" antes del cierre que agrega el router
        + char_count.count_chars(closing_tags())
    )
    budget = char_count.TWEET_CHAR_LIMIT - reserved

    body = f"{anniversary.headline} ({anniversary.era_name}). {anniversary.detail}"
    if anniversary.today_connection:
        with_connection = f"{body}\n{anniversary.today_connection}"
        if char_count.count_chars(with_connection) <= budget:
            body = with_connection
    if char_count.count_chars(body) > budget:
        body = _truncate(body, budget)

    return "\n".join([header, body, question])


def format_anniversary_quick_fact_plain(anniversary: Anniversary, is_exact: bool, today: date | None = None) -> str:
    if today is None:
        today = date.today()
    years_ago = today.year - anniversary.year

    if is_exact:
        prefix = f"📌 Dato rapido: un {anniversary.day:02d}/{anniversary.month:02d} de {anniversary.year}"
    else:
        prefix = (
            f"📌 Dato rapido (no es de hoy, del {anniversary.day:02d}/{anniversary.month:02d}/"
            f"{anniversary.year}, hace {years_ago} años)"
        )

    # Mismo presupuesto defensivo que format_anniversary_plain: el prefijo es
    # fijo y corto, lo que puede desbordar es el resto (texto libre curado).
    reserved = char_count.count_chars(prefix) + 2 + 2 + char_count.count_chars(closing_tags())
    budget = char_count.TWEET_CHAR_LIMIT - reserved

    body = f"{anniversary.headline.lower()} ({anniversary.era_name}): {anniversary.detail}"
    if char_count.count_chars(body) > budget:
        body = _truncate(body, budget)

    return f"{prefix}, {body}"


def closing_tags() -> str:
    # No se arroba a equipos historicos: los nombres/handles de esas epocas
    # (ej. "Vodafone Giants") no siempre coinciden con la cuenta actual de la
    # misma organizacion (ej. "GIANTX"), asi que arrobar por nombre historico
    # arriesgaria etiquetar la cuenta equivocada.
    parts = [settings.league_handle_les, "#OnThisDay", *settings.custom_hashtag_list]
    return " ".join(parts)
