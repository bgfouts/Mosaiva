import pytest
from fastapi.testclient import TestClient

from app.services.records import confidence_to_probability
from app.services.seed import load_theories


def test_confidence_labels_become_an_internal_estimate():
    assert confidence_to_probability("High") == pytest.approx(0.80)
    assert confidence_to_probability("Very Low") == pytest.approx(0.08)
    assert confidence_to_probability("Low–Moderate / insufficient evidence") == pytest.approx(0.35)
    assert confidence_to_probability("High for rash; Low–Moderate for sleepiness") == pytest.approx(0.575)
    assert confidence_to_probability("Moderate as amplifier; Low as primary cause") == pytest.approx(0.375)
    assert confidence_to_probability("not a known label") == pytest.approx(0.5)


def test_confidence_label_sets_the_internal_estimate_unless_one_is_sent(client):
    created = client.post(
        "/api/hypotheses",
        json={"title": "A new theory", "confidence": "Very Low", "likely_role": "Very unlikely"},
    )
    assert created.status_code == 201
    assert created.json()["probability"] == pytest.approx(0.08)
    assert created.json()["confidence"] == "Very Low"

    explicit = client.post(
        "/api/hypotheses",
        json={"title": "Named estimate", "confidence": "High", "probability": 0.99},
    )
    assert explicit.json()["probability"] == pytest.approx(0.95)

    changed = client.patch(
        f"/api/hypotheses/{created.json()['id']}",
        json={"confidence": "High"},
    )
    assert changed.json()["probability"] == pytest.approx(0.80)
    held = client.patch(
        f"/api/hypotheses/{created.json()['id']}",
        json={"statement": "Edited description only."},
    )
    assert held.json()["probability"] == pytest.approx(0.80)
    assert held.json()["statement"] == "Edited description only."


def test_seed_inserts_each_spreadsheet_theory_once(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIVA_DATABASE_URL", f"sqlite:///{tmp_path / 'seed.db'}")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("MOSAIVA_MOSAIC_FIXTURE", "1")
    monkeypatch.setenv("MOSAIVA_RESEARCH_FIXTURE", "")
    monkeypatch.setenv("MOSAIVA_DISABLE_LIVE_SEARCH", "1")
    monkeypatch.setenv("MOSAIVA_SEED_HYPOTHESES", "1")
    monkeypatch.setenv("MOSAIVA_SEED_RESEARCH", "0")
    from app.db import reset_engine
    from app.settings import get_settings

    get_settings.cache_clear()
    reset_engine()
    from app.main import create_app

    theories = load_theories()
    with TestClient(create_app()) as client:
        rows = client.get("/api/hypotheses").json()
    assert len(rows) == 27
    assert len(theories) == 27
    assert rows[0]["title"] == "Migraine-spectrum disorder / silent migraine"
    assert rows[0]["confidence"] == "High"
    assert rows[0]["likely_role"] == "Primary explanation"
    assert rows[0]["statement"].startswith("Migraine can produce")
    assert rows[0]["why_it_fits"].startswith("Stereotyped facial/head pain")
    assert rows[0]["probability"] == pytest.approx(0.80)
    assert rows[-1]["title"] == "Primary CNS autoimmune/inflammatory disease"
    assert [row["title"] for row in rows] == [theory["title"] for theory in theories]

    with TestClient(create_app()) as client:
        again = client.get("/api/hypotheses").json()
    assert len(again) == 27
    assert [row["id"] for row in again] == [row["id"] for row in rows]
    reset_engine()
    get_settings.cache_clear()
