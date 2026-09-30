from collections.abc import Generator

from sqlalchemy import create_engine, event
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
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args)
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
