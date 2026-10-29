from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url


def make_engine(database_url: str, echo: bool = False) -> Engine:
    """Create an engine for SQLite (local) or Postgres (e.g. Supabase) from DATABASE_URL."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return create_engine(url, echo=echo, pool_pre_ping=True)

    if url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, echo=echo, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:  # enforce FKs like Postgres does
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return engine
