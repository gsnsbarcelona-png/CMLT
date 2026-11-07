from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.services import ai_service


def _fake_response(status_code, json_data=None, reason="Error"):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status_code=status_code, request=request, json=json_data or {})


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "anthropic_api_key", "sk-ant-test")


def test_not_configured_raises_without_calling_api(monkeypatch, mocker):
    monkeypatch.setattr(ai_service.settings, "anthropic_api_key", "")
    create_mock = mocker.patch("anthropic.resources.Messages.create")
    with pytest.raises(ai_service.AIGenerationError):
        ai_service.generate_tweet("un tema")
    create_mock.assert_not_called()


def test_successful_generation_returns_text(mocker):
    fake_message = SimpleNamespace(content=[SimpleNamespace(type="text", text="Este es el tweet generado.")])
    mocker.patch("anthropic.resources.Messages.create", return_value=fake_message)

    result = ai_service.generate_tweet("lanzamiento de producto", tone="entusiasta")

    assert result == "Este es el tweet generado."


def test_authentication_error_translated(mocker):
    response = _fake_response(401, {"error": {"message": "invalid api key"}})
    error = anthropic.AuthenticationError("invalid api key", response=response, body=None)
    mocker.patch("anthropic.resources.Messages.create", side_effect=error)

    with pytest.raises(ai_service.AIGenerationError, match="invalida"):
        ai_service.generate_tweet("un tema")


def test_rate_limit_error_translated(mocker):
    response = _fake_response(429, {"error": {"message": "rate limited"}})
    error = anthropic.RateLimitError("rate limited", response=response, body=None)
    mocker.patch("anthropic.resources.Messages.create", side_effect=error)

    with pytest.raises(ai_service.AIGenerationError, match="limite"):
        ai_service.generate_tweet("un tema")


def test_connection_error_translated(mocker):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.APIConnectionError(request=request)
    mocker.patch("anthropic.resources.Messages.create", side_effect=error)

    with pytest.raises(ai_service.AIGenerationError, match="conectar"):
        ai_service.generate_tweet("un tema")


def test_generate_hype_calendar_passes_matches_as_context(mocker):
    fake_message = SimpleNamespace(content=[SimpleNamespace(type="text", text="Semana decisiva en la LES!")])
    create_mock = mocker.patch("anthropic.resources.Messages.create", return_value=fake_message)

    result = ai_service.generate_hype_calendar("Mar 01/09 17:00 UCAM vs BAR (Final)", "LES")

    assert result == "Semana decisiva en la LES!"
    _, kwargs = create_mock.call_args
    assert "UCAM vs BAR" in kwargs["messages"][0]["content"]
    assert "LES" in kwargs["messages"][0]["content"]
    assert kwargs["system"] == ai_service.CALENDAR_HYPE_SYSTEM_PROMPT


def test_generate_hype_calendar_not_configured(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "anthropic_api_key", "")
    with pytest.raises(ai_service.AIGenerationError):
        ai_service.generate_hype_calendar("algun partido", "LES")


def test_generate_stat_tweet_passes_fact_as_context(mocker):
    fake_message = SimpleNamespace(content=[SimpleNamespace(type="text", text="KDA del split!")])
    create_mock = mocker.patch("anthropic.resources.Messages.create", return_value=fake_message)

    result = ai_service.generate_stat_tweet("Escik cerro el split con 9.4 de KDA.", "Escik")

    assert result == "KDA del split!"
    _, kwargs = create_mock.call_args
    assert "Escik cerro el split con 9.4 de KDA." in kwargs["messages"][0]["content"]
    assert "Escik" in kwargs["messages"][0]["content"]
    assert kwargs["system"] == ai_service.STAT_SYSTEM_PROMPT


def test_generate_stat_tweet_not_configured(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "anthropic_api_key", "")
    with pytest.raises(ai_service.AIGenerationError):
        ai_service.generate_stat_tweet("algun dato", "alguien")


def test_generate_head_to_head_variant_passes_context_and_angle(mocker):
    fake_message = SimpleNamespace(content=[SimpleNamespace(type="text", text="UCAM vs Barca hoy!")])
    create_mock = mocker.patch("anthropic.resources.Messages.create", return_value=fake_message)

    result = ai_service.generate_head_to_head_variant("Historial directo: 1-1.", "historial")

    assert result == "UCAM vs Barca hoy!"
    _, kwargs = create_mock.call_args
    assert "Historial directo: 1-1." in kwargs["messages"][0]["content"]
    assert "historial" in kwargs["messages"][0]["content"]
    assert kwargs["system"] == ai_service.HEAD_TO_HEAD_PREVIEW_SYSTEM_PROMPT


def test_generate_head_to_head_variant_not_configured(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "anthropic_api_key", "")
    with pytest.raises(ai_service.AIGenerationError):
        ai_service.generate_head_to_head_variant("algun contexto", "forma reciente")


def test_generate_anniversary_tweet_passes_context(mocker):
    fake_message = SimpleNamespace(content=[SimpleNamespace(type="text", text="Un dia como hoy...")])
    create_mock = mocker.patch("anthropic.resources.Messages.create", return_value=fake_message)

    result = ai_service.generate_anniversary_tweet("Hecho: Vodafone Giants campeon.")

    assert result == "Un dia como hoy..."
    _, kwargs = create_mock.call_args
    assert "Hecho: Vodafone Giants campeon." in kwargs["messages"][0]["content"]
    assert kwargs["system"] == ai_service.ANNIVERSARY_SYSTEM_PROMPT


def test_generate_anniversary_tweet_not_configured(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "anthropic_api_key", "")
    with pytest.raises(ai_service.AIGenerationError):
        ai_service.generate_anniversary_tweet("algun contexto")


def test_generate_anniversary_quick_fact_passes_context(mocker):
    fake_message = SimpleNamespace(content=[SimpleNamespace(type="text", text="Dato rapido...")])
    create_mock = mocker.patch("anthropic.resources.Messages.create", return_value=fake_message)

    result = ai_service.generate_anniversary_quick_fact("Hecho: Vodafone Giants campeon.")

    assert result == "Dato rapido..."
    _, kwargs = create_mock.call_args
    assert "Hecho: Vodafone Giants campeon." in kwargs["messages"][0]["content"]
    assert kwargs["system"] == ai_service.ANNIVERSARY_QUICK_FACT_SYSTEM_PROMPT


def test_generate_anniversary_quick_fact_not_configured(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "anthropic_api_key", "")
    with pytest.raises(ai_service.AIGenerationError):
        ai_service.generate_anniversary_quick_fact("algun contexto")


def test_generate_league_comparison_variant_passes_context(mocker):
    fake_message = SimpleNamespace(content=[SimpleNamespace(type="text", text="Sabias que...")])
    create_mock = mocker.patch("anthropic.resources.Messages.create", return_value=fake_message)

    result = ai_service.generate_league_comparison_variant("Tono pedido: debate\nDato real: 2.13 vs 1.6")

    assert result == "Sabias que..."
    _, kwargs = create_mock.call_args
    assert "Tono pedido: debate" in kwargs["messages"][0]["content"]
    assert kwargs["system"] == ai_service.LEAGUE_COMPARISON_SYSTEM_PROMPT


def test_generate_league_comparison_variant_not_configured(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "anthropic_api_key", "")
    with pytest.raises(ai_service.AIGenerationError):
        ai_service.generate_league_comparison_variant("algun contexto")


def test_generate_individual_duel_variant_passes_context(mocker):
    fake_message = SimpleNamespace(content=[SimpleNamespace(type="text", text="Duelo de mid...")])
    create_mock = mocker.patch("anthropic.resources.Messages.create", return_value=fake_message)

    result = ai_service.generate_individual_duel_variant("9.4 de KDA vs 4.0 de KDA", "Escik vs Fulano")

    assert result == "Duelo de mid..."
    _, kwargs = create_mock.call_args
    assert "Escik vs Fulano" in kwargs["messages"][0]["content"]
    assert "9.4 de KDA vs 4.0 de KDA" in kwargs["messages"][0]["content"]
    assert kwargs["system"] == ai_service.INDIVIDUAL_DUEL_SYSTEM_PROMPT


def test_generate_individual_duel_variant_not_configured(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "anthropic_api_key", "")
    with pytest.raises(ai_service.AIGenerationError):
        ai_service.generate_individual_duel_variant("algun dato", "A vs B")


def test_generate_top_ranking_variant_passes_context_and_variant(mocker):
    fake_message = SimpleNamespace(content=[SimpleNamespace(type="text", text="Top KDA...")])
    create_mock = mocker.patch("anthropic.resources.Messages.create", return_value=fake_message)

    result = ai_service.generate_top_ranking_variant("Categoria: KDA (LES 2026 Summer).\n1. Escik - 9.4", "top1")

    assert result == "Top KDA..."
    _, kwargs = create_mock.call_args
    assert "Variante pedida: top1" in kwargs["messages"][0]["content"]
    assert "1. Escik - 9.4" in kwargs["messages"][0]["content"]
    assert kwargs["system"] == ai_service.TOP_RANKING_SYSTEM_PROMPT


def test_generate_top_ranking_variant_not_configured(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "anthropic_api_key", "")
    with pytest.raises(ai_service.AIGenerationError):
        ai_service.generate_top_ranking_variant("algun contexto", "top3")
