"""Formateadores de texto (variante sin IA) de cada tipo de tweet de stats."""
from app.services.golgg.config import get_current_tournament
from app.services.golgg.models import HeadToHeadPreviewData, LeagueComparisonCandidate, StatCandidate, TopRankingCandidate
from app.services.golgg.top_ranking import TOP_RANKING_CATEGORIES, TOP_RANKING_TOP_N
from app.services.phrasing import vary_question


def format_h2h_variant_plain(preview: HeadToHeadPreviewData, angle: str, today_context: str | None = None) -> str:
    """Texto de la preview head-to-head. Misma idea de las 4 partes
    (gancho / dato protagonista / matiz / pregunta) con frases fijas por
    angulo, usando solo los datos reales que haya -- si algo falta, frase
    neutra en vez de inventar."""
    total = preview.total_wins_a + preview.total_wins_b
    lines = [f"🥊 {preview.team_a} 🆚 {preview.team_b}"]
    if today_context:
        lines.append(today_context)

    if angle == "historial":
        if total:
            headline = (
                f"Historial de la temporada: {preview.team_a} {preview.total_wins_a}-"
                f"{preview.total_wins_b} {preview.team_b} (mapas: {preview.total_maps_a}-{preview.total_maps_b})."
            )
        else:
            headline = f"Primer cruce del año entre {preview.team_a} y {preview.team_b} esta temporada."

        if preview.last_meeting:
            nuance = f"El último cruce ({preview.last_meeting.date}) lo ganó {preview.last_meeting.winner}."
        else:
            nuance = "Todavía no hay antecedentes directos esta temporada."

        question = vary_question("¿Se repite la historia hoy?")
    else:
        parts = []
        for team, form in ((preview.team_a, preview.recent_form_a), (preview.team_b, preview.recent_form_b)):
            parts.append(f"{team} {form.wins}V-{form.losses}D" if form else f"{team} sin datos recientes")
        headline = f"Forma reciente: {' / '.join(parts)}."

        if total:
            leader = preview.team_a if preview.total_wins_a >= preview.total_wins_b else preview.team_b
            nuance = f"En el historial de la temporada manda {leader} ({preview.total_wins_a}-{preview.total_wins_b})."
        else:
            nuance = "Sin cruces previos esta temporada para comparar."

        question = vary_question("¿Quién llega mejor hoy?")

    lines.extend([headline, nuance, f"{question} 👀"])
    return "\n".join(lines)


def format_stat_tweet_plain(candidate: StatCandidate) -> str:
    return (
        f"{candidate.emoji} {candidate.hook or candidate.title}\n"
        f"{candidate.fact_sentence}\n"
        f"{vary_question(candidate.question)} {candidate.emoji}"
    )


def format_league_comparison_plain(candidate: LeagueComparisonCandidate, tone: str) -> str:
    if tone == "debate":
        header = f"🤔 {candidate.hook}" if candidate.hook else "🤔 DEBATE LES-LEC"
        question = vary_question("¿Se sostendría esa cifra en la LEC?") + " 👀"
    else:
        header = f"🔎 {candidate.hook}" if candidate.hook else "🔎 DATO LES-LEC"
        question = vary_question("¿Aguantaría el ritmo LEC?") + " 👀"

    # Con gancho, este ya trae las dos cifras (LES y LEC): repetir la frase
    # larga se pasaria de 280 con las arrobas de cierre.
    body = [] if candidate.hook else [candidate.fact_sentence]
    lines = [header, *body, candidate.nuance, question]
    return "\n".join(lines)


def _top_ranking_lead(candidate: TopRankingCandidate) -> tuple[str, str]:
    """(gancho, frase de comparacion con el segundo o '') con datos reales del top."""
    leader = candidate.entries[0]
    spec = TOP_RANKING_CATEGORIES.get(candidate.kind.removeprefix("top_"))
    head = f"{leader.name} lleva {leader.value_display} {candidate.unit_label}"
    if len(candidate.entries) < 2 or spec is None:
        return f"{head}: el mejor de {candidate.total_pool_size} con datos", ""
    second = candidate.entries[1]
    diff = abs(leader.value - second.value)
    if diff == 0:
        return f"{head}, igualado con {second.name}", ""
    diff_text = spec.value_formatter(diff)
    comparative = "menos" if spec.ascending else "más"
    hook = f"{head}: {diff_text} {comparative} que {second.name}, el segundo"
    return hook, ""


def format_top_ranking_plain(candidate: TopRankingCandidate, variant: str) -> str:
    tournament = get_current_tournament()
    hook, _ = _top_ranking_lead(candidate)
    lines = [f"{candidate.emoji} {hook}", f"{candidate.category_label} · {tournament}"]

    if variant == "top1":
        leader = candidate.entries[0]
        lines.append(f"Puesto 1 de {candidate.total_pool_size} con datos suficientes, en {leader.games} partidos.")
        if candidate.league_average_display:
            lines.append(f"Media de la liga: {candidate.league_average_display} {candidate.unit_label}.")
        lines.append(f"{vary_question('¿Se mantiene arriba?')} {candidate.emoji}")
    else:
        if candidate.total_pool_size < TOP_RANKING_TOP_N:
            lines.append(f"Solo hay {candidate.total_pool_size} con datos suficientes este split:")
        for i, entry in enumerate(candidate.entries, start=1):
            lines.append(f"{i}. {entry.name} — {entry.value_display} {candidate.unit_label}")
        if candidate.league_average_display:
            lines.append(f"Media de la liga: {candidate.league_average_display} {candidate.unit_label}.")
        lines.append(f"{vary_question('¿Se mantiene el top 1?')} {candidate.emoji}")

    return "\n".join(lines)
