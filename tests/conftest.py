import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app


@pytest.fixture(autouse=True)
def _deterministic_phrasing(monkeypatch):
    """La variedad de redaccion es aleatoria: apagada, los tests ven siempre
    las frases originales. Se prueba aparte, activandola."""
    from app.services import phrasing

    monkeypatch.setattr(phrasing, "VARIETY_ENABLED", False)
    phrasing.reset_recent()
    yield


@pytest.fixture(autouse=True)
def _no_prewarm_and_clear_events_cache(monkeypatch):
    """Sin precalentamiento al arrancar (pegaria a la red) y con la cache del
    calendario limpia entre tests."""
    from app.config import settings
    from app.services import lolesports_service

    monkeypatch.setattr(settings, "prewarm_cache", False)
    lolesports_service._events_cache.clear()
    yield
    lolesports_service._events_cache.clear()


@pytest.fixture(autouse=True)
def _disable_golgg_autodiscover(monkeypatch):
    """Los tests usan los torneos del settings; el autodescubrimiento (que
    pega a gol.gg) se prueba aparte, activandolo explicitamente."""
    from app.config import settings
    from app.services import golgg_service

    monkeypatch.setattr(settings, "golgg_autodiscover", False)
    # warm_urls descarga paginas reales en paralelo: en tests, sin red.
    monkeypatch.setattr(golgg_service, "warm_urls", lambda urls: None)
    golgg_service.reset_active_config_cache()
    yield
    golgg_service.reset_active_config_cache()


@pytest.fixture(autouse=True)
def _clear_golgg_cache():
    """La cache de gol.gg es un dict a nivel de modulo -- sin esto, tests
    distintos que mockean la misma URL con HTML distinto se pisarian entre si."""
    from app.services import golgg_service

    golgg_service._http_cache.clear()
    yield


@pytest.fixture(autouse=True)
def _clear_ranked_cache():
    """Misma razon que _clear_golgg_cache, pero para la cache de lolpros.gg."""
    from app.services import ranked_service

    ranked_service._http_cache.clear()
    ranked_service._negative_cache.clear()
    yield


@pytest.fixture(autouse=True)
def _clear_logo_cache():
    """Cache de bytes de escudos: sin limpiar, tests que mockean la misma URL
    con respuestas distintas se pisarian."""
    from app.services import image_service

    image_service.clear_logo_cache()
    yield


@pytest.fixture(autouse=True)
def _clear_lolesports_teams_cache():
    """Misma razon que _clear_golgg_cache, pero para la cache de getTeams."""
    from app.services import lolesports_service

    lolesports_service._teams_cache = None
    yield


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    # /api/health abre su propia sesion con el engine global: en CI no existe
    # la carpeta data/, asi que se apunta al engine temporal del test.
    monkeypatch.setattr("app.main.engine", engine)
    yield TestClient(app)
    app.dependency_overrides.clear()
