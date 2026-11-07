"""Comparativa LES-LEC."""
import random

from app.services.golgg.models import GolGGError, LeagueComparisonCandidate, PlayerStat, StatFocusNotFoundError, TeamStat


def _average(entries: list, attr: str) -> float:
    return round(sum(getattr(e, attr) for e in entries) / len(entries), 2)


LEVEL_NUANCE = "Ojo: son ligas de nivel y muestra distintos, no equivale 1 a 1."


def compute_league_comparison_candidates(
    les_teams: list[TeamStat],
    les_players: list[PlayerStat],
    lec_teams: list[TeamStat],
    lec_players: list[PlayerStat],
) -> list[LeagueComparisonCandidate]:
    """Candidatos LES-vs-LEC: mejor de LES en una metrica contra el promedio
    de LEC en esa misma metrica. Se limita a metricas donde esta comparacion
    (mejor-de-LES vs promedio-de-LEC) no suene despectiva hacia la LES -- se
    evitan a proposito metricas de ritmo/economia (GPM, CSM) donde la LEC
    suele ser estructuralmente mas alta y la comparacion quedaria injusta."""
    candidates: list[LeagueComparisonCandidate] = []

    if les_teams and lec_teams:
        best_kda = max(les_teams, key=lambda t: t.kda)
        lec_avg_kda = _average(lec_teams, "kda")
        candidates.append(
            LeagueComparisonCandidate(
                kind="team_kda",
                subject=best_kda.name,
                fact_sentence=(
                    f"{best_kda.name} tiene un ratio K:D de {best_kda.kda} en la LES, frente al "
                    f"{lec_avg_kda} de promedio entre los equipos de la LEC."
                ),
                nuance=LEVEL_NUANCE,
            )
        )

        best_winrate = max(les_teams, key=lambda t: t.win_rate)
        lec_avg_winrate = _average(lec_teams, "win_rate")
        candidates.append(
            LeagueComparisonCandidate(
                kind="team_winrate",
                subject=best_winrate.name,
                fact_sentence=(
                    f"{best_winrate.name} lidera la LES con {best_winrate.win_rate}% de victorias, "
                    f"frente al {lec_avg_winrate}% de promedio en la LEC."
                ),
                nuance=LEVEL_NUANCE,
            )
        )

        best_fb = max(les_teams, key=lambda t: t.fb_pct)
        lec_avg_fb = _average(lec_teams, "fb_pct")
        candidates.append(
            LeagueComparisonCandidate(
                kind="team_fb",
                subject=best_fb.name,
                fact_sentence=(
                    f"{best_fb.name} se lleva la primera sangre en el {best_fb.fb_pct}% de sus "
                    f"partidos en la LES, frente al {lec_avg_fb}% de promedio en la LEC."
                ),
                nuance=LEVEL_NUANCE,
            )
        )

    if les_players and lec_players:
        best_kda = max(les_players, key=lambda p: p.kda)
        lec_avg_kda = _average(lec_players, "kda")
        candidates.append(
            LeagueComparisonCandidate(
                kind="player_kda",
                subject=best_kda.name,
                fact_sentence=(
                    f"{best_kda.name} cerro con {best_kda.kda} de KDA en la LES, frente al "
                    f"{lec_avg_kda} de promedio entre los jugadores de la LEC."
                ),
                nuance="El KDA en la LES suele estar inflado vs la LEC por la diferencia de nivel.",
            )
        )

    return candidates


def pick_league_comparison_candidate(
    candidates: list[LeagueComparisonCandidate], focus: str | None = None
) -> LeagueComparisonCandidate:
    pool = candidates
    if focus:
        focus_lower = focus.strip().lower()
        pool = [c for c in candidates if focus_lower in c.subject.lower()]
        if not pool:
            raise StatFocusNotFoundError(f"No encontramos datos de '{focus}' para comparar con la LEC.")
    if not pool:
        raise GolGGError("No hay datos suficientes de LES y LEC todavia para comparar.")
    return random.choice(pool)
