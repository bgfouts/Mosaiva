import pytest
from fastapi.testclient import TestClient

from app.services.seed import load_potential_interventions


def test_seed_inserts_each_potential_intervention_once(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIVA_DATABASE_URL", f"sqlite:///{tmp_path / 'seed.db'}")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("MOSAIVA_MOSAIC_FIXTURE", "1")
    monkeypatch.setenv("MOSAIVA_RESEARCH_FIXTURE", "")
    monkeypatch.setenv("MOSAIVA_DISABLE_LIVE_SEARCH", "1")
    monkeypatch.setenv("MOSAIVA_SEED_HYPOTHESES", "1")
    monkeypatch.setenv("MOSAIVA_SEED_INTERVENTIONS", "1")
    from app.db import reset_engine
    from app.settings import get_settings

    get_settings.cache_clear()
    reset_engine()
    from app.main import create_app

    expected = load_potential_interventions()
    with TestClient(create_app()) as client:
        rows = client.get("/api/interventions").json()
    assert len(rows) == 24
    assert len(expected) == 24
    assert [row["name"] for row in rows] == [item["name"] for item in expected]
    assert all(row["dose"] == "" for row in rows)

    ajovy = rows[0]
    assert ajovy["name"] == "Start Ajovy (30-day injectable)"
    assert ajovy["category"] == "medication"
    assert ajovy["status"] == "ask_clinician"
    assert "clinician" in ajovy["clinician_task"].lower()
    assert "do not start" in ajovy["clinician_task"].lower()

    luvox = next(row for row in rows if row["name"].startswith("Reduce Luvox"))
    assert luvox["dose"] == ""
    assert luvox["status"] == "ask_clinician"
    assert "150 mg" in luvox["name"]
    assert "do not change" in luvox["clinician_task"].lower()

    magnesium = next(row for row in rows if "magnesium" in row["name"])
    assert magnesium["category"] == "supplement"
    assert magnesium["status"] == "potential"

    culture = next(row for row in rows if row["name"].startswith("Urine culture"))
    assert any("UTI" in title["title"] for title in culture["hypotheses"])

    with TestClient(create_app()) as client:
        again = client.get("/api/interventions").json()
    assert [row["id"] for row in again] == [row["id"] for row in rows]
    reset_engine()
    get_settings.cache_clear()
