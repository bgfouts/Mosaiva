import os

import pytest
from fastapi.testclient import TestClient


def _database_url(tmp_path) -> str:
    """Use MOSAIVA_TEST_DATABASE_URL to run the suite against Postgres; each test starts empty."""
    url = os.environ.get("MOSAIVA_TEST_DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{tmp_path / 'test.db'}"
    from sqlalchemy import create_engine

    from app import models  # noqa: F401
    from app.db import Base
    from app.settings import Settings

    engine = create_engine(Settings(MOSAIVA_DATABASE_URL=url).database_url)
    Base.metadata.drop_all(engine)
    engine.dispose()
    return url


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIVA_DATABASE_URL", _database_url(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("MOSAIVA_MOSAIC_FIXTURE", "1")
    monkeypatch.setenv("MOSAIVA_RESEARCH_FIXTURE", "")
    monkeypatch.setenv("MOSAIVA_DISABLE_LIVE_SEARCH", "1")
    monkeypatch.setenv("MOSAIVA_SEED_HYPOTHESES", "0")
    monkeypatch.setenv("MOSAIVA_SEED_INTERVENTIONS", "0")
    monkeypatch.setenv("MOSAIVA_SEED_RESEARCH", "0")
    monkeypatch.setenv("MOSAIVA_COACH_PLAN_FIXTURE", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "")
    monkeypatch.setenv("BLOB_STORE_ID", "")
    from app.db import reset_engine
    from app.settings import get_settings

    get_settings.cache_clear()
    reset_engine()
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    reset_engine()
    get_settings.cache_clear()
