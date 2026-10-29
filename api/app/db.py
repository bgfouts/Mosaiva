from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import get_settings

_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    pass


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def reset_engine() -> None:
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None


def get_engine() -> Engine:
    global _engine, SessionLocal
    if _engine is None:
        url = get_settings().database_url
        if url.startswith("sqlite"):
            _engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            # Neon's pooled endpoint runs PgBouncer in transaction mode, so server-side
            # prepared statements must stay off. Serverless instances keep the pool small.
            _engine = create_engine(
                url,
                connect_args={"prepare_threshold": None},
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=3,
                pool_recycle=300,
            )
        SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def init_db() -> None:
    from app import models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(engine)
    _ensure_hypothesis_columns(engine)


def _ensure_hypothesis_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(hypotheses)").fetchall()
        names = {row[1] for row in rows}
        additions = {
            "why_it_fits": "TEXT DEFAULT ''",
            "confidence": "TEXT DEFAULT ''",
            "likely_role": "TEXT DEFAULT ''",
            "position": "INTEGER DEFAULT 0",
        }
        for column, ddl in additions.items():
            if column not in names:
                conn.exec_driver_sql(f"ALTER TABLE hypotheses ADD COLUMN {column} {ddl}")
        intervention_rows = conn.exec_driver_sql("PRAGMA table_info(interventions)").fetchall()
        intervention_names = {row[1] for row in intervention_rows}
        if "position" not in intervention_names:
            conn.exec_driver_sql("ALTER TABLE interventions ADD COLUMN position INTEGER DEFAULT 0")
        session_rows = conn.exec_driver_sql("PRAGMA table_info(coach_sessions)").fetchall()
        session_names = {row[1] for row in session_rows}
        session_additions = {
            "ask_since_last": "BOOLEAN DEFAULT 0",
            "plan_status": "TEXT DEFAULT 'pending'",
            "planned_questions": "TEXT DEFAULT '[]'",
        }
        for column, ddl in session_additions.items():
            if column not in session_names:
                conn.exec_driver_sql(f"ALTER TABLE coach_sessions ADD COLUMN {column} {ddl}")


@contextmanager
def startup_lock() -> Iterator[None]:
    """Serialize schema setup and seeding when several serverless instances start at once."""
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        yield
        return
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(727134)"))
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(727134)"))
            conn.commit()


def open_session() -> Session:
    if SessionLocal is None:
        get_engine()
    assert SessionLocal is not None
    return SessionLocal()


def get_db() -> Generator[Session, None, None]:
    db = open_session()
    try:
        yield db
    finally:
        db.close()
