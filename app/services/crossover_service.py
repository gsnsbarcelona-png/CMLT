import json
from dataclasses import dataclass
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "les_lec_players.json"


class CrossoverDataError(Exception):
    pass


@dataclass
class PlayerCrossover:
    player: str
    fact: str
    context: str
    source: str


def load_crossovers() -> list[PlayerCrossover]:
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CrossoverDataError(f"No se pudo leer la base de cruces LES-LEC ({DATA_PATH}).") from exc

    return [
        PlayerCrossover(
            player=entry["player"],
            fact=entry["fact"],
            context=entry["context"],
            source=entry.get("source", ""),
        )
        for entry in raw
    ]


def compute_player_crossover_candidates() -> list:
    # Import tardio para no crear una dependencia circular a nivel de modulo
    # (golgg_service no necesita saber nada de crossover_service).
    from app.services.golgg_service import LeagueComparisonCandidate

    return [
        LeagueComparisonCandidate(
            kind="player_crossover",
            subject=crossover.player,
            fact_sentence=crossover.fact,
            nuance=crossover.context,
        )
        for crossover in load_crossovers()
    ]
