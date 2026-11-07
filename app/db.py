import os
from collections.abc import Generator

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)


def _add_column_if_missing(table: str, column: str, column_type: str) -> None:
    """SQLModel.metadata.create_all() solo crea tablas que no existen, nunca
    altera columnas de una tabla que ya existe -- no hay Alembic en este
    proyecto. Para una base `tweets.db` real ya en uso, un campo nuevo en el
    modelo necesita este ALTER TABLE manual (envuelto en try/except: si la
    columna ya existe, SQLite tira OperationalError y se ignora -- lo hace
    seguro de correr en cada arranque, no solo la primera vez)."""
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))
    except OperationalError:
        pass  # la columna ya existe (o la tabla no existe todavia -- create_all() la crea completa despues)


def init_db() -> None:
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_url.removeprefix("sqlite:///")
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    _add_column_if_missing("tweet", "image_url", "TEXT")


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
