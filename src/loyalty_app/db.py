from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from loyalty_app.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(database_url: str) -> None:
    if database_url.startswith("sqlite:///"):
        raw_path = database_url.removeprefix("sqlite:///")
        if raw_path and raw_path != ":memory:":
            Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


def _normalize_database_url(database_url: str) -> str:
    """Hosting platforms (Render, Heroku, ...) hand out Postgres connection
    strings as ``postgres://`` or driver-less ``postgresql://`` - normalize
    either to the psycopg3 driver SQLAlchemy needs, so pasting the platform's
    connection string in as-is just works without manual editing."""
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    return database_url


def build_engine(database_url: str | None = None) -> Engine:
    """Create the SQLAlchemy engine.

    For SQLite we follow the standard SQLAlchemy recipe to take manual control of
    transaction BEGIN statements: every transaction is opened with ``BEGIN IMMEDIATE``,
    which acquires SQLite's database-wide write lock up front (rather than at the
    first write statement). This serializes all balance-changing operations and
    avoids lost-update races, at the cost of allowing only one writer at a time -
    an accepted, documented trade-off at this application's scale (see
    docs/ARCHITECTURE_DECISIONS.md). A ``busy_timeout`` makes a blocked transaction
    wait instead of failing immediately.

    On Postgres, transactions behave normally and per-row locking is instead
    achieved with ``SELECT ... FOR UPDATE`` in the query itself (see
    loyalty_app.loyalty.service), so the same call sites work unchanged.
    """
    settings = get_settings()
    url = _normalize_database_url(database_url or settings.database_url)
    _ensure_sqlite_dir(url)

    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}

    engine = create_engine(url, connect_args=connect_args, future=True)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_connection, _connection_record):  # noqa: ANN001
            # Hand transaction control to us instead of pysqlite's implicit behavior.
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        @event.listens_for(engine, "begin")
        def _on_begin(conn):  # noqa: ANN001
            conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


engine: Engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
