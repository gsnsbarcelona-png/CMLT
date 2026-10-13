import json

import pytest

from app.services.crossover_service import (
    CrossoverDataError,
    PlayerCrossover,
    compute_player_crossover_candidates,
    load_crossovers,
)


def test_load_crossovers_reads_real_data_file():
    crossovers = load_crossovers()
    assert len(crossovers) >= 2
    assert all(isinstance(c, PlayerCrossover) for c in crossovers)
    assert all(c.player and c.fact and c.context for c in crossovers)


def test_load_crossovers_missing_file_raises(monkeypatch, tmp_path):
    import app.services.crossover_service as crossover_service

    monkeypatch.setattr(crossover_service, "DATA_PATH", tmp_path / "no_existe.json")
    with pytest.raises(CrossoverDataError):
        load_crossovers()


def test_compute_player_crossover_candidates_builds_league_comparison_candidates(monkeypatch, tmp_path):
    import app.services.crossover_service as crossover_service

    entries = [{"player": "Jugador X", "fact": "Dato real X", "context": "Contexto X", "source": "Fuente X"}]
    data_path = tmp_path / "crossovers.json"
    data_path.write_text(json.dumps(entries), encoding="utf-8")
    monkeypatch.setattr(crossover_service, "DATA_PATH", data_path)

    candidates = compute_player_crossover_candidates()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind == "player_crossover"
    assert candidate.subject == "Jugador X"
    assert candidate.fact_sentence == "Dato real X"
    assert candidate.nuance == "Contexto X"
