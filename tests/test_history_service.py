import json
from datetime import date

import pytest

from app.services import char_count
from app.services.history_service import (
    Anniversary,
    HistoryDataError,
    closing_tags,
    find_for_date,
    find_for_today,
    find_nearest,
    format_anniversary_context,
    format_anniversary_plain,
    format_anniversary_quick_fact_plain,
    load_anniversaries,
)


def test_load_anniversaries_reads_real_data_file():
    anniversaries = load_anniversaries()
    assert len(anniversaries) >= 6
    assert all(isinstance(a, Anniversary) for a in anniversaries)
    assert all(1 <= a.month <= 12 and 1 <= a.day <= 31 for a in anniversaries)


def test_load_anniversaries_missing_file_raises(monkeypatch, tmp_path):
    import app.services.history_service as history_service

    monkeypatch.setattr(history_service, "DATA_PATH", tmp_path / "no_existe.json")
    with pytest.raises(HistoryDataError):
        load_anniversaries()


@pytest.fixture()
def fake_data(monkeypatch, tmp_path):
    entries = [
        {
            "month": 8, "day": 12, "year": 2021,
            "headline": "Hecho A", "detail": "Detalle A", "era_name": "Superliga",
            "teams": ["Equipo X", "Equipo Y"], "today_connection": "Sigue activo.", "source": "Fuente A",
        },
        {
            "month": 9, "day": 2, "year": 2018,
            "headline": "Hecho B", "detail": "Detalle B", "era_name": "Superliga Orange",
            "teams": [], "today_connection": None, "source": "Fuente B",
        },
    ]
    data_path = tmp_path / "anniversaries.json"
    data_path.write_text(json.dumps(entries), encoding="utf-8")

    import app.services.history_service as history_service

    monkeypatch.setattr(history_service, "DATA_PATH", data_path)
    return entries


def test_find_for_date_exact_match(fake_data):
    found = find_for_date(8, 12)
    assert found is not None
    assert found.headline == "Hecho A"


def test_find_for_date_no_match_returns_none(fake_data):
    assert find_for_date(1, 1) is None


def test_find_nearest_picks_closest_with_wraparound(fake_data):
    # 15/12 esta mas cerca del 02/09 (dando la vuelta al año) o del 12/08?
    # dist a 12/08 desde 15/12: ~125 dias. dist a 02/09 desde 15/12: ~104 dias.
    anniversary, days = find_nearest(12, 15)
    assert anniversary.headline == "Hecho B"
    assert days < 125


def test_find_for_today_exact(fake_data):
    anniversary, is_exact, days = find_for_today(today=date(2026, 8, 12))
    assert is_exact is True
    assert days == 0
    assert anniversary.headline == "Hecho A"


def test_find_for_today_nearest_when_no_exact_match(fake_data):
    anniversary, is_exact, days = find_for_today(today=date(2026, 8, 15))
    assert is_exact is False
    assert days > 0


def test_find_for_today_empty_database_raises(monkeypatch, tmp_path):
    import app.services.history_service as history_service

    empty_path = tmp_path / "empty.json"
    empty_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(history_service, "DATA_PATH", empty_path)

    with pytest.raises(HistoryDataError):
        find_for_today(today=date(2026, 8, 12))


def _anniversary(**overrides):
    base = dict(
        month=8, day=12, year=2021, headline="Hecho A", detail="Detalle A", era_name="Superliga",
        teams=["Equipo X", "Equipo Y"], today_connection="Sigue activo.", source="Fuente A",
    )
    base.update(overrides)
    return Anniversary(**base)


def test_format_anniversary_context_exact_states_it_clearly():
    context = format_anniversary_context(_anniversary(), is_exact=True, today=date(2026, 8, 12))
    assert "EXACTAMENTE hoy" in context
    assert "hace 5 años" in context
    assert "Hecho: Hecho A." in context
    assert "Sigue activo." in context


def test_format_anniversary_context_not_exact_states_it_clearly():
    context = format_anniversary_context(_anniversary(), is_exact=False, today=date(2026, 8, 20))
    assert "No hay ninguna efemeride verificada para el dia de hoy exacto" in context
    assert "12/08/2021" in context


def test_format_anniversary_plain_exact():
    text = format_anniversary_plain(_anniversary(), is_exact=True, today=date(2026, 8, 12))
    assert "UN DIA COMO HOY, hace 5 años (2021)" in text
    assert "Hecho A (Superliga). Detalle A" in text
    assert "Sigue activo." in text
    assert "¿Lo viviste en directo? 👀" in text


def test_format_anniversary_plain_not_exact_says_so():
    text = format_anniversary_plain(_anniversary(), is_exact=False, today=date(2026, 8, 20))
    assert "No es de hoy exacto" in text
    assert "12/08/2021" in text


def test_format_anniversary_plain_never_exceeds_char_limit_with_long_detail():
    # Regresion: un detalle largo combinado con el encabezado "no exacto"
    # llegaba a pasarse del limite de 280 (visto en vivo con un caso real:
    # 286 caracteres). Ahora se recorta con "…" para garantizar el limite
    # pase lo que pase el largo del dato curado.
    long_anniversary = _anniversary(
        headline="Un titulo bastante largo para forzar el desborde del limite",
        detail="Un detalle todavia mas largo, con cifras y contexto de sobra como para "
        "que sumado al encabezado y al resto del tweet se pase claramente de 280 caracteres.",
        today_connection="Y ademas una conexion con la actualidad que tambien suma bastante texto.",
    )
    for is_exact in (True, False):
        text = format_anniversary_plain(long_anniversary, is_exact=is_exact, today=date(2026, 8, 20))
        full_tweet = f"{text}\n\n{closing_tags()}"
        assert char_count.count_chars(full_tweet) <= char_count.TWEET_CHAR_LIMIT


def test_format_anniversary_plain_short_detail_is_not_truncated():
    text = format_anniversary_plain(_anniversary(), is_exact=True, today=date(2026, 8, 12))
    assert "…" not in text
    assert "Detalle A" in text


def test_format_anniversary_quick_fact_is_short_and_states_missing_data():
    exact = format_anniversary_quick_fact_plain(_anniversary(), is_exact=True, today=date(2026, 8, 12))
    assert exact.startswith("📌 Dato rapido: un 12/08 de 2021")

    not_exact = format_anniversary_quick_fact_plain(_anniversary(), is_exact=False, today=date(2026, 8, 20))
    assert "no es de hoy" in not_exact


def test_format_anniversary_quick_fact_never_exceeds_char_limit_with_long_detail():
    long_anniversary = _anniversary(
        headline="Un titulo bastante largo para forzar el desborde del limite",
        detail="Un detalle todavia mas largo, con cifras y contexto de sobra como para "
        "que sumado al resto del tweet se pase claramente de 280 caracteres en total.",
    )
    for is_exact in (True, False):
        text = format_anniversary_quick_fact_plain(long_anniversary, is_exact=is_exact, today=date(2026, 8, 20))
        full_tweet = f"{text}\n\n{closing_tags()}"
        assert char_count.count_chars(full_tweet) <= char_count.TWEET_CHAR_LIMIT


def test_closing_tags_no_team_handles(monkeypatch):
    import app.services.history_service as history_service

    monkeypatch.setattr(history_service.settings, "league_handle_les", "@LESESPORTS")
    monkeypatch.setattr(history_service.settings, "custom_hashtags", "#LT")

    tags = closing_tags()
    assert tags == "@LESESPORTS #OnThisDay #LT"
