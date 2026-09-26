from app.services.mosaic import MosaicValidationError, validate_review


def _snapshot():
    return {
        "hypotheses": [
            {"id": 1, "title": "Fragmented sleep", "probability": 0.5, "status": "active"}
        ],
        "evidence": [{"id": 7, "text": "Wakes at 3am", "hypothesis_id": 1}],
        "interventions": [],
        "papers": [{"id": 3, "title": "A paper", "hypothesis_ids": [1]}],
    }


def test_two_recommendations_are_rejected():
    raw = {
        "hypothesis_updates": [],
        "recommendation": [
            {"action": "hold", "dose": ""},
            {"action": "add", "name": "Walk", "category": "lifestyle", "dose": ""},
        ],
    }
    try:
        validate_review(_snapshot(), raw)
    except MosaicValidationError as exc:
        assert "one recommendation" in exc.message.lower()
    else:
        raise AssertionError("expected rejection")


def test_medication_dose_is_rejected_and_probabilities_clamp():
    raw = {
        "hypothesis_updates": [
            {
                "hypothesis_id": 1,
                "probability": 0.01,
                "rationale": "Still uncertain.",
                "evidence_ids": [7],
                "paper_ids": [3],
            }
        ],
        "recommendation": {
            "action": "add",
            "name": "Example drug",
            "category": "medication",
            "dose": "5 mg",
            "safety_note": "Ask your clinician before starting this.",
            "rationale": "Worth a conversation.",
            "what_to_watch": "Nothing until you have spoken with them.",
        },
    }
    try:
        validate_review(_snapshot(), raw)
    except MosaicValidationError as exc:
        assert "dose" in exc.message.lower()
    else:
        raise AssertionError("expected dose rejection")

    raw["recommendation"]["dose"] = ""
    validated = validate_review(_snapshot(), raw)
    assert validated["hypothesis_updates"][0]["probability"] == 0.05
    assert validated["recommendation"]["dose"] == ""


def test_prescribed_removal_must_mention_a_clinician_and_self_directed_need_not():
    snapshot = _snapshot()
    snapshot["interventions"] = [
        {
            "id": 4,
            "name": "Nightly tablet",
            "category": "medication",
            "status": "active",
            "benefit": 1,
            "side_effect_burden": 5,
            "clinician_prescribed": True,
            "hypothesis_ids": [1],
        }
    ]
    base = {
        "hypothesis_updates": [],
        "recommendation": {
            "action": "remove",
            "intervention_id": 4,
            "name": "Nightly tablet",
            "category": "medication",
            "dose": "",
            "rationale": "Burden is high.",
            "what_to_watch": "Sleep and side effects.",
            "safety_note": "Stop it tonight.",
        },
    }
    try:
        validate_review(snapshot, base)
    except MosaicValidationError as exc:
        assert "clinician" in exc.message.lower()
    else:
        raise AssertionError("expected clinician framing")

    base["recommendation"]["safety_note"] = "Discuss stopping with your clinician."
    assert validate_review(snapshot, base)["recommendation"]["action"] == "remove"

    snapshot["interventions"][0]["clinician_prescribed"] = False
    snapshot["interventions"][0]["category"] = "supplement"
    base["recommendation"]["safety_note"] = "You started this yourself, so you can stop it."
    base["recommendation"]["category"] = "supplement"
    assert validate_review(snapshot, base)["recommendation"]["action"] == "remove"


def test_weekly_review_is_reused_and_decisions_follow_prescriber(client):
    client.post("/api/hypotheses", json={"title": "Fragmented sleep", "probability": 0.6})
    prescribed = client.post(
        "/api/interventions",
        json={
            "name": "Nightly tablet",
            "category": "medication",
            "clinician_prescribed": True,
            "benefit": 1,
            "side_effect_burden": 5,
            "dose": "as prescribed",
        },
    ).json()
    first = client.post("/api/mosaic/run")
    assert first.status_code == 200
    review = first.json()
    assert review["recommendation"]["action"] == "remove"
    assert "clinician" in review["recommendation"]["safety_note"].lower()

    second = client.post("/api/mosaic/run")
    assert second.status_code == 200
    assert second.json()["id"] == review["id"]

    accepted = client.post(f"/api/mosaic/{review['id']}/decision", json={"decision": "accept"})
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    kept = client.get("/api/interventions").json()
    match = next(row for row in kept if row["id"] == prescribed["id"])
    assert match["status"] == "active"
    assert "clinician" in match["clinician_task"].lower()

    again = client.post(f"/api/mosaic/{review['id']}/decision", json={"decision": "dismiss"})
    assert again.status_code == 409


def test_self_directed_removal_stops_the_intervention(client):
    client.post("/api/hypotheses", json={"title": "Meal timing", "probability": 0.55})
    created = client.post(
        "/api/interventions",
        json={
            "name": "Late snack",
            "category": "diet",
            "benefit": 1,
            "side_effect_burden": 4,
        },
    ).json()
    review = client.post("/api/mosaic/run").json()
    assert review["recommendation"]["action"] == "remove"
    client.post(f"/api/mosaic/{review['id']}/decision", json={"decision": "accept"})
    stopped = client.get("/api/interventions").json()[0]
    assert stopped["id"] == created["id"]
    assert stopped["status"] == "stopped"
    assert stopped["stop_date"]
