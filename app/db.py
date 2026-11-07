import os
from collections.abc import Generator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

def _normalize_database_url(url: str) -> str:
    """Neon/Supabase/Render dan "postgres://..." o "postgresql://...", que
    SQLAlchemy 2 no acepta tal cual (el primero) o resuelve a un driver que
    no instalamos (psycopg2). Se fuerza el driver psycopg (v3)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


DATABASE_URL = _normalize_database_url(settings.database_url)
_is_sqlite = DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
# pool_pre_ping: Neon suspende las conexiones inactivas; sin esto la primera
# consulta tras un rato falla con "connection closed".
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=not _is_sqlite)


def _add_column_if_missing(table: str, column: str, column_type: str) -> None:
    """SQLModel.metadata.create_all() solo crea tablas que no existen, nunca
    altera columnas de una tabla que ya existe -- no hay Alembic en este
    proyecto. Para una base `tweets.db` real ya en uso, un campo nuevo en el
    modelo necesita este ALTER TABLE manual (envuelto en try/except: si la
    columna ya existe, SQLite tira OperationalError y se ignora -- lo hace
    seguro de correr en cada arranque, no solo la primera vez). Se mira primero
    con el inspector (en vez de capturar el error) porque en Postgres un
    ALTER duplicado deja la transaccion rota."""
    inspector = inspect(engine)
    if not inspector.has_table(table):
        return  # create_all() la crea completa
    if column in {c["name"] for c in inspector.get_columns(table)}:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))


def init_db() -> None:
    if DATABASE_URL.startswith("sqlite:///"):
        db_path = DATABASE_URL.removeprefix("sqlite:///")
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    _add_column_if_missing("tweet", "image_url", "TEXT")


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
