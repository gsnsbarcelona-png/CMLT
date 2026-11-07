import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app


@pytest.fixture(autouse=True)
def _disable_golgg_autodiscover(monkeypatch):
    """Los tests usan los torneos del settings; el autodescubrimiento (que
    pega a gol.gg) se prueba aparte, activandolo explicitamente."""
    from app.config import settings
    from app.services import golgg_service

    monkeypatch.setattr(settings, "golgg_autodiscover", False)
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
    yield


@pytest.fixture(autouse=True)
def _clear_lolesports_teams_cache():
    """Misma razon que _clear_golgg_cache, pero para la cache de getTeams."""
    from app.services import lolesports_service

    lolesports_service._teams_cache = None
    yield


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()
