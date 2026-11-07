"""Candidatos de stats curiosas (mejor equipo/jugador por métrica) y arrobas de cierre."""
import random

from app.config import settings
from app.services.golgg.config import get_current_tournament
from app.services.golgg.models import GolGGError, PlayerStat, StatCandidate, StatFocusNotFoundError, TeamStat
from app.services.phrasing import choose


def _fmt(value: float) -> str:
    return f"{round(value, 2):g}"


def _context(pool: list, attr: str, best, unit: str = "") -> tuple[str, bool]:
    """Comparacion con datos reales de la liga: (frase, supera_al_segundo).
    Frase vacia si no hay con quien comparar (nunca se inventa)."""
    others = sorted((e for e in pool if e is not best), key=lambda e: getattr(e, attr), reverse=True)
    if not others:
        return "", False
    second = others[0]
    avg = sum(getattr(e, attr) for e in pool) / len(pool)
    sv = getattr(second, attr)
    suffix = f"{unit}" if unit else ""
    sentence = (
        f"Media de la liga: {_fmt(avg)}{suffix}; el segundo, {second.name}, {_fmt(sv)}{suffix}."
    )
    # 'clear' = ventaja de al menos un 20% sobre el segundo: solo entonces se
    # permite el 'nadie se le acerca'; si no, el gancho se limita al dato.
    return sentence, getattr(best, attr) >= sv * 1.2


def _join(fact: str, context: str) -> str:
    return f"{fact} {context}" if context else fact


def compute_candidates(
    team_stats: list[TeamStat], player_stats: list[PlayerStat], categories: set[str]
) -> list[StatCandidate]:
    candidates: list[StatCandidate] = []

    if "teams" in categories and team_stats:
        best_kda = max(team_stats, key=lambda t: t.kda)
        ctx, clear = _context(team_stats, "kda", best_kda)
        hook = choose(
            [
                f"{best_kda.name} lleva {best_kda.kda} de K:D: nadie en la liga se le acerca",
                f"{best_kda.name} manda en K:D con {best_kda.kda}, lo mejor de la liga",
            ]
            if clear
            else [f"{best_kda.name} lidera el K:D de la liga con {best_kda.kda}"]
        )
        candidates.append(
            StatCandidate(
                kind="team_kda",
                subject=best_kda.name,
                fact_sentence=_join(
                    f"{best_kda.name} tiene el mejor ratio K:D de la liga: {best_kda.kda} ({best_kda.games} partidos jugados).",
                    ctx,
                ),
                emoji="⚔️",
                title="RATIO DE MUERTES DEL SPLIT",
                question="¿Alguien lo va a superar antes de que termine el split?",
                hook=hook,
            )
        )

        best_winrate = max(team_stats, key=lambda t: t.win_rate)
        wins = round(best_winrate.games * best_winrate.win_rate / 100)
        ctx, clear = _context(team_stats, "win_rate", best_winrate, "%")
        hook = choose(
            [
                f"{best_winrate.name} gana el {best_winrate.win_rate}% de sus partidos: nadie en la liga lo hace mejor",
                f"{best_winrate.name} manda con un {best_winrate.win_rate}% de victorias",
            ]
            if clear
            else [f"{best_winrate.name} lidera la liga con un {best_winrate.win_rate}% de victorias"]
        )
        candidates.append(
            StatCandidate(
                kind="team_winrate",
                subject=best_winrate.name,
                fact_sentence=_join(
                    f"{best_winrate.name} lidera el winrate de la liga con {best_winrate.win_rate}% ({wins}-{best_winrate.games - wins}).",
                    ctx,
                ),
                emoji="📈",
                title="EL MEJOR REGISTRO DE LA LIGA",
                question="¿Quién le puede parar el paso?",
                hook=hook,
            )
        )

        best_fb = max(team_stats, key=lambda t: t.fb_pct)
        ctx, clear = _context(team_stats, "fb_pct", best_fb, "%")
        hook = choose(
            [
                f"{best_fb.name} saca la primera sangre en el {best_fb.fb_pct}% de sus partidos: nadie más",
                f"{best_fb.name} se adelanta en el {best_fb.fb_pct}% de sus partidos, el mejor dato de la liga",
            ]
            if clear
            else [f"{best_fb.name} se lleva la primera sangre en el {best_fb.fb_pct}% de sus partidos"]
        )
        candidates.append(
            StatCandidate(
                kind="team_fb",
                subject=best_fb.name,
                fact_sentence=_join(
                    f"{best_fb.name} se lleva la primera sangre en el {best_fb.fb_pct}% de sus partidos, el mejor registro de la liga.",
                    ctx,
                ),
                emoji="🩸",
                title="SIEMPRE PRIMEROS EN SANGRAR",
                question="¿Es la clave de su temporada?",
                hook=hook,
            )
        )

        if len(team_stats) >= 2:
            worst_winrate = min(team_stats, key=lambda t: t.win_rate)
            if worst_winrate.name != best_winrate.name:
                gap = round(best_winrate.win_rate - worst_winrate.win_rate, 1)
                candidates.append(
                    StatCandidate(
                        kind="team_winrate_contrast",
                        subject=f"{best_winrate.name} vs {worst_winrate.name}",
                        fact_sentence=(
                            f"{best_winrate.name} lidera la liga con {best_winrate.win_rate}% de victorias, "
                            f"mientras {worst_winrate.name} tiene el peor registro con {worst_winrate.win_rate}%."
                        ),
                        emoji="⚖️",
                        title="LAS DOS CARAS DE LA LIGA",
                        question="¿Se cruzan antes de que termine el split?",
                        hook=(
                            f"{_fmt(gap)} puntos de winrate separan a {best_winrate.name} "
                            f"({best_winrate.win_rate}%) de {worst_winrate.name} ({worst_winrate.win_rate}%)"
                        ),
                    )
                )

    if "players" in categories and player_stats:
        best_kda = max(player_stats, key=lambda p: p.kda)
        ctx, clear = _context(player_stats, "kda", best_kda)
        hook = choose(
            [
                f"{best_kda.name} lleva {best_kda.kda} de KDA: nadie en la liga se le acerca",
                f"{best_kda.name} manda en KDA con {best_kda.kda} en {best_kda.games} partidos",
            ]
            if clear
            else [f"{best_kda.name} lidera el KDA de la liga con {best_kda.kda}"]
        )
        candidates.append(
            StatCandidate(
                kind="player_kda",
                subject=best_kda.name,
                fact_sentence=_join(
                    f"{best_kda.name} cerró el split con {best_kda.kda} de KDA en {best_kda.games} partidos.", ctx
                ),
                emoji="🔥",
                title="KDA DEL SPLIT",
                question="¿Puede sostener ese nivel bajo presión?",
                hook=hook,
            )
        )

        best_csm = max(player_stats, key=lambda p: p.csm)
        ctx, clear = _context(player_stats, "csm", best_csm)
        hook = choose(
            [
                f"{best_csm.name} promedia {best_csm.csm} de CSM: nadie farmea más en la liga",
                f"{best_csm.name} manda en farmeo con {best_csm.csm} CS por minuto",
            ]
            if clear
            else [f"{best_csm.name} lidera el farmeo de la liga con {best_csm.csm} de CSM"]
        )
        candidates.append(
            StatCandidate(
                kind="player_csm",
                subject=best_csm.name,
                fact_sentence=_join(f"{best_csm.name} promedia {best_csm.csm} de CSM, el mejor farmeo de la liga.", ctx),
                emoji="🌾",
                title="LA MEJOR FARMEADA DE LA LIGA",
                question="¿Eso alcanza para ganarle a las junglas rivales?",
                hook=hook,
            )
        )

        best_solo = max(player_stats, key=lambda p: p.solo_kills)
        if best_solo.solo_kills > 0:
            ctx, clear = _context(player_stats, "solo_kills", best_solo)
            hook = (
                f"{best_solo.name} suma {best_solo.solo_kills} solo kills: nadie gana más 1v1 en la liga"
                if clear
                else f"{best_solo.name} lidera las solo kills de la liga con {best_solo.solo_kills}"
            )
            candidates.append(
                StatCandidate(
                    kind="player_solo_kills",
                    subject=best_solo.name,
                    fact_sentence=_join(
                        f"{best_solo.name} acumula {best_solo.solo_kills} solo kills este split, el máximo de la liga.", ctx
                    ),
                    emoji="🗡️",
                    title="EL QUE MÁS 1V1 GANA",
                    question="¿Te animas a duelear contra él?",
                    hook=hook,
                )
            )

        best_penta = max(player_stats, key=lambda p: p.penta_kills)
        if best_penta.penta_kills > 0:
            n = best_penta.penta_kills
            plural = "pentakill" if n == 1 else "pentakills"
            candidates.append(
                StatCandidate(
                    kind="player_penta_kills",
                    subject=best_penta.name,
                    fact_sentence=f"{best_penta.name} suma {n} {plural} este split.",
                    emoji="💥",
                    title="PENTAKILL",
                    question="¿Viste el clip?",
                    hook=f"{best_penta.name} suma {n} {plural} este split, el máximo de la liga",
                )
            )

    return candidates


def pick_candidate(candidates: list[StatCandidate], focus: str | None = None) -> StatCandidate:
    pool = candidates
    if focus:
        focus_lower = focus.strip().lower()
        pool = [c for c in candidates if focus_lower in c.subject.lower()]
        if not pool:
            raise StatFocusNotFoundError(f"No encontramos datos de '{focus}' en {get_current_tournament()}.")
    if not pool:
        raise GolGGError(f"No hay datos estadísticos disponibles para {get_current_tournament()} todavía.")
    return random.choice(pool)


TEAM_LEVEL_KINDS = {
    "team_kda",
    "team_winrate",
    "team_fb",
    "team_winrate_contrast",
    "team_head_to_head",
    "team_rank_vs_team",
    "individual_duel",  # el candidato real tiene subject "JugadorA vs JugadorB";
    # las arrobas de equipo salen de un StatCandidate sintetico con subject
    # "EquipoA vs EquipoB" armado aparte solo para el cierre (igual que H2H).
    "top_team_towers",
    "top_team_dragons",
    "top_team_fb",
    "top_team_fastest",
    # top_player_kda y top_player_csm NO estan aca a proposito: son
    # categorias de jugador, no arroban equipo (gol.gg no expone el equipo
    # de cada jugador en la tabla de stats, no se inventa).
}


def get_team_handles() -> dict[str, str]:
    """Parsea settings.team_handles ("Nombre:@handle,Nombre:@handle,...").

    Cargado a mano por el usuario -- no se adivinan handles de equipo."""
    handles: dict[str, str] = {}
    for entry in settings.team_handles.split(","):
        if ":" not in entry:
            continue
        name, handle = entry.split(":", 1)
        name, handle = name.strip(), handle.strip()
        if name and handle:
            handles[name] = handle
    return handles


def stat_closing_tags(candidate: StatCandidate) -> str:
    """Arrobas de equipo (solo si el candidato es de nivel equipo) + arroba de
    liga + hashtags personalizados, para agregar al final de un tweet de stats."""
    team_handles: list[str] = []
    if candidate.kind in TEAM_LEVEL_KINDS:
        handles_map = get_team_handles()
        team_names = [n.strip() for n in candidate.subject.split(" vs ")]
        team_handles = [handles_map[name] for name in team_names if name in handles_map]

    parts = team_handles + [settings.league_handle_les] + settings.custom_hashtag_list
    return " ".join(parts)
