import re

from fastapi.testclient import TestClient

from app.services.seed import load_seed_papers


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIVA_DATABASE_URL", f"sqlite:///{tmp_path / 'seed.db'}")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("MOSAIVA_MOSAIC_FIXTURE", "1")
    monkeypatch.setenv("MOSAIVA_RESEARCH_FIXTURE", "")
    monkeypatch.setenv("MOSAIVA_DISABLE_LIVE_SEARCH", "1")
    monkeypatch.setenv("MOSAIVA_SEED_HYPOTHESES", "1")
    monkeypatch.setenv("MOSAIVA_SEED_INTERVENTIONS", "1")
    monkeypatch.setenv("MOSAIVA_SEED_RESEARCH", "1")
    from app.db import reset_engine
    from app.settings import get_settings

    get_settings.cache_clear()
    reset_engine()
    from app.main import create_app

    return create_app()


def test_default_client_does_not_seed_research(client):
    assert client.get("/api/research").json() == []


def test_seed_inserts_each_open_access_paper_once(tmp_path, monkeypatch):
    app = _client(tmp_path, monkeypatch)
    expected = load_seed_papers()
    with TestClient(app) as client:
        papers = client.get("/api/research").json()
        hypotheses = {row["title"]: row["id"] for row in client.get("/api/hypotheses").json()}
        interventions = {row["name"]: row["id"] for row in client.get("/api/interventions").json()}

    assert len(papers) == len(expected) == 18
    assert [row["title"] for row in papers] == [item["title"] for item in expected]
    assert all(row["pdf_url"].startswith("https://pmc.ncbi.nlm.nih.gov/articles/") for row in papers)
    assert all(row["excerpt"] for row in papers)

    by_query = {row["query"]: row for row in papers}
    ajovy = by_query["seed:PMC9951598"]
    assert hypotheses["Migraine-spectrum disorder / silent migraine"] in ajovy["hypothesis_ids"]
    assert interventions["Start Ajovy (30-day injectable)"] in ajovy["intervention_ids"]
    assert "clinician" in ajovy["relevance_note"].lower()

    luvox = by_query["seed:PMC11802704"]
    assert interventions["Reduce Luvox from 150 mg to 100 mg"] in luvox["intervention_ids"]
    assert not re.search(r"\d+(\.\d+)?\s*mg\b", luvox["relevance_note"], flags=re.I)
    assert "milligram" not in luvox["relevance_note"].lower()

    magnesium = by_query["seed:PMC11858643"]
    assert "not an instruction to start or stop" in magnesium["relevance_note"]

    glp = by_query["seed:PMC13485101"]
    assert "not a reason to start" in glp["relevance_note"].lower()
    assert hypotheses["Intracranial hypertension (IIH)"] in glp["hypothesis_ids"]

    with TestClient(app) as client:
        again = client.get("/api/research").json()
    assert [row["id"] for row in again] == [row["id"] for row in papers]

    from app.db import reset_engine
    from app.settings import get_settings

    reset_engine()
    get_settings.cache_clear()
