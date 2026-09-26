import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIVA_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("MOSAIVA_MOSAIC_FIXTURE", "1")
    monkeypatch.setenv("MOSAIVA_RESEARCH_FIXTURE", "")
    monkeypatch.setenv("MOSAIVA_DISABLE_LIVE_SEARCH", "1")
    from app.db import reset_engine
    from app.settings import get_settings

    get_settings.cache_clear()
    reset_engine()
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    reset_engine()
    get_settings.cache_clear()
