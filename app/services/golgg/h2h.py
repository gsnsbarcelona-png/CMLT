"""Resultados de partidos y head-to-head entre equipos."""
from app.services.golgg import client
from app.services.golgg.client import GOLGG_BASE, _fetch_table
from app.services.golgg.models import HeadToHeadPreviewData, MatchResult, RecentForm, StatCandidate


def fetch_match_results(tournament: str) -> list[MatchResult]:
    url = f"{GOLGG_BASE}/tournament/tournament-matchlist/{tournament}/"
    table = _fetch_table(url, "table_list")
    rows = table.find_all("tr")[1:]

    # Esta tabla tiene headers vacios para las columnas de equipos (a diferencia
    # de teams/list y players/list), asi que no se puede parsear por nombre de
    # columna -- los equipos siempre estan en las celdas 1 y 3 (indices fijos,
    # verificados contra el HTML real), PERO cual de los dos gano NO es fijo por
    # posicion: gol.gg marca al ganador con la clase css "text_victory" en la
    # celda que le corresponda (a veces la 1, a veces la 3). Ignorar esto y
    # asumir que la celda 1 siempre es el ganador invierte el resultado en esos
    # casos -- confirmado con un partido real (UCAM le gano a Barca en la
    # celda 3, marcado "text_victory" ahi y no en la celda 1). El score de la
    # celda 2 siempre viene en el orden "celda1 - celda3" (no "ganador-perdedor"),
    # asi que hay que reordenarlo segun quien gano para sacar mapas ganados/perdidos.
    results: list[MatchResult] = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        team_1, team_2 = cells[1], cells[3]
        name_1, name_2 = team_1.get_text(strip=True), team_2.get_text(strip=True)
        score_text = cells[2].get_text(strip=True)
        date_text = cells[6].get_text(strip=True) if len(cells) > 6 else ""
        if not name_1 or not name_2:
            continue

        score_parts = [p.strip() for p in score_text.split("-")]
        if len(score_parts) != 2:
            continue
        try:
            maps_1, maps_2 = int(score_parts[0]), int(score_parts[1])
        except ValueError:
            continue

        if "text_victory" in (team_1.get("class") or []):
            winner, loser = name_1, name_2
            winner_maps, loser_maps = maps_1, maps_2
        elif "text_victory" in (team_2.get("class") or []):
            winner, loser = name_2, name_1
            winner_maps, loser_maps = maps_2, maps_1
        else:
            # No se pudo determinar el ganador por clase css -> se descarta la
            # fila en vez de arriesgarse a invertir el resultado.
            continue

        results.append(
            MatchResult(
                winner=winner,
                loser=loser,
                winner_maps=winner_maps,
                loser_maps=loser_maps,
                date=date_text,
                tournament=tournament,
            )
        )
    return results


def fetch_all_match_results(tournaments: list[str]) -> list[MatchResult]:
    client.warm_urls([f"{GOLGG_BASE}/tournament/tournament-matchlist/{t}/" for t in tournaments])
    all_results: list[MatchResult] = []
    for tournament in tournaments:
        all_results.extend(fetch_match_results(tournament))
    return all_results


def find_head_to_head(team_a: str, team_b: str, tournaments: list[str]) -> StatCandidate | None:
    """Busca el candidato de rivalidad de un par puntual de equipos elegido por el usuario."""
    wanted = {team_a.strip().lower(), team_b.strip().lower()}
    for candidate in compute_head_to_head_candidates(tournaments):
        parts = {p.strip().lower() for p in candidate.subject.split(" vs ")}
        if parts == wanted:
            return candidate
    return None


def compute_head_to_head_candidates(tournaments: list[str]) -> list[StatCandidate]:
    all_results = fetch_all_match_results(tournaments)

    pair_wins: dict[frozenset, dict[str, int]] = {}
    pair_maps: dict[frozenset, dict[str, int]] = {}
    for result in all_results:
        pair = frozenset({result.winner, result.loser})
        if len(pair) != 2:
            continue
        record = pair_wins.setdefault(pair, {})
        record[result.winner] = record.get(result.winner, 0) + 1

        maps_record = pair_maps.setdefault(pair, {})
        maps_record[result.winner] = maps_record.get(result.winner, 0) + result.winner_maps
        maps_record[result.loser] = maps_record.get(result.loser, 0) + result.loser_maps

    candidates: list[StatCandidate] = []
    for pair, record in pair_wins.items():
        team_a, team_b = sorted(pair)
        wins_a = record.get(team_a, 0)
        wins_b = record.get(team_b, 0)
        total = wins_a + wins_b
        if total == 0:
            continue

        maps_record = pair_maps.get(pair, {})
        maps_a = maps_record.get(team_a, 0)
        maps_b = maps_record.get(team_b, 0)

        if wins_a == wins_b:
            fact = (
                f"{team_a} y {team_b} se repartieron sus {total} cruces de la temporada: "
                f"{wins_a}-{wins_b} (mapas: {maps_a}-{maps_b})."
            )
        else:
            leader, leader_wins, leader_maps, other, other_wins, other_maps = (
                (team_a, wins_a, maps_a, team_b, wins_b, maps_b)
                if wins_a > wins_b
                else (team_b, wins_b, maps_b, team_a, wins_a, maps_a)
            )
            fact = (
                f"{leader} le ganó a {other} en {leader_wins} de sus {total} cruces esta temporada "
                f"({leader_wins}-{other_wins}, mapas: {leader_maps}-{other_maps})."
            )

        candidates.append(
            StatCandidate(
                kind="team_head_to_head",
                subject=f"{team_a} vs {team_b}",
                fact_sentence=fact,
                emoji="🤜🤛",
                title="RIVALIDAD DEL AÑO",
                question="¿Se repite la historia la próxima vez que se crucen?",
            )
        )
    return candidates


def _recent_form(team: str, all_results: list[MatchResult], n: int = 5) -> RecentForm | None:
    team_results = [r for r in all_results if team in (r.winner, r.loser)]
    if not team_results:
        return None
    team_results.sort(key=lambda r: r.date, reverse=True)
    recent = team_results[:n]
    wins = sum(1 for r in recent if r.winner == team)
    return RecentForm(wins=wins, losses=len(recent) - wins, games=len(recent))


def build_head_to_head_preview(team_a: str, team_b: str, tournaments: list[str]) -> HeadToHeadPreviewData:
    all_results = fetch_all_match_results(tournaments)
    pair_results = [r for r in all_results if {r.winner, r.loser} == {team_a, team_b}]

    wins_by_a = [r for r in pair_results if r.winner == team_a]
    wins_by_b = [r for r in pair_results if r.winner == team_b]

    return HeadToHeadPreviewData(
        team_a=team_a,
        team_b=team_b,
        total_wins_a=len(wins_by_a),
        total_wins_b=len(wins_by_b),
        total_maps_a=sum(r.winner_maps if r.winner == team_a else r.loser_maps for r in pair_results),
        total_maps_b=sum(r.winner_maps if r.winner == team_b else r.loser_maps for r in pair_results),
        last_meeting=max(pair_results, key=lambda r: r.date) if pair_results else None,
        last_win_by_a=max(wins_by_a, key=lambda r: r.date) if wins_by_a else None,
        last_win_by_b=max(wins_by_b, key=lambda r: r.date) if wins_by_b else None,
        recent_form_a=_recent_form(team_a, all_results),
        recent_form_b=_recent_form(team_b, all_results),
    )
