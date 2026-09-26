def test_hypothesis_probability_is_clamped_and_can_be_removed(client):
    created = client.post(
        "/api/hypotheses",
        json={"title": "Fragmented sleep", "statement": "Wake-ups drive the fatigue.", "probability": 0.99},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["probability"] == 0.95
    assert body["statement"] == "Wake-ups drive the fatigue."

    listed = client.get("/api/hypotheses")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    removed = client.delete(f"/api/hypotheses/{body['id']}")
    assert removed.status_code == 204
    assert client.get("/api/hypotheses").json() == []


def test_intervention_add_remove_and_rejects_dose_on_unstarted_medicine(client):
    hypothesis = client.post("/api/hypotheses", json={"title": "Histamine load", "probability": 0.4}).json()
    created = client.post(
        "/api/interventions",
        json={
            "name": "Low histamine breakfast",
            "category": "diet",
            "benefit": 2,
            "side_effect_burden": 4,
            "hypothesis_ids": [hypothesis["id"]],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["net_value"] == -2
    assert body["hypothesis_ids"] == [hypothesis["id"]]

    rejected = client.post(
        "/api/interventions",
        json={
            "name": "Example drug",
            "category": "medication",
            "status": "ask_clinician",
            "dose": "10 mg",
        },
    )
    assert rejected.status_code == 422
    assert "dose" in str(rejected.json()["detail"]).lower()

    removed = client.delete(f"/api/interventions/{body['id']}")
    assert removed.status_code == 204
    assert client.get("/api/interventions").json() == []


def test_settings_reject_unknown_timezone(client):
    bad = client.patch("/api/settings", json={"timezone": "Not/AZone"})
    assert bad.status_code == 422
    good = client.patch("/api/settings", json={"timezone": "America/Los_Angeles"})
    assert good.status_code == 200
    assert good.json()["timezone"] == "America/Los_Angeles"
